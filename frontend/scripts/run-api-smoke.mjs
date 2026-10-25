import { spawn } from "node:child_process";
import { createServer } from "node:net";
import { randomBytes } from "node:crypto";
import { existsSync } from "node:fs";
import { mkdtemp, realpath, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = resolve(frontendRoot, "..");
const backendRoot = join(repositoryRoot, "backend");
const venvPython = process.platform === "win32"
  ? join(repositoryRoot, ".venv", "Scripts", "python.exe")
  : join(repositoryRoot, ".venv", "bin", "python");
const python = existsSync(venvPython) ? venvPython : (process.env.PYTHON || "python");
const viteCli = join(frontendRoot, "node_modules", "vite", "bin", "vite.js");
const playwrightCli = join(frontendRoot, "node_modules", "@playwright", "test", "cli.js");
const serviceErrors = new WeakMap();

function sqliteUrl(filePath) {
  const normalized = encodeURI(filePath.replaceAll("\\", "/"));
  return process.platform === "win32"
    ? `sqlite:///${normalized}`
    : `sqlite:////${normalized.replace(/^\/+/, "")}`;
}

function runCommand(command, args, options, label) {
  return new Promise((resolvePromise, rejectPromise) => {
    const child = spawn(command, args, {
      cwd: options.cwd,
      env: options.env,
      stdio: "inherit",
      windowsHide: true,
    });
    child.once("error", rejectPromise);
    child.once("exit", (code, signal) => {
      if (code === 0) resolvePromise();
      else rejectPromise(new Error(`${label} a échoué (code=${code}, signal=${signal ?? "aucun"}).`));
    });
  });
}

function startService(command, args, options, label) {
  const child = spawn(command, args, {
    cwd: options.cwd,
    env: options.env,
    stdio: "inherit",
    windowsHide: true,
  });
  child.on("error", (error) => {
    serviceErrors.set(child, error);
    console.error(`${label} : ${error.message}`);
  });
  return child;
}

async function freePort() {
  const server = createServer();
  await new Promise((resolvePromise, rejectPromise) => {
    server.once("error", rejectPromise);
    server.listen(0, "127.0.0.1", resolvePromise);
  });
  const address = server.address();
  if (!address || typeof address === "string") throw new Error("Port local indisponible.");
  const { port } = address;
  await new Promise((resolvePromise, rejectPromise) => {
    server.close((error) => error ? rejectPromise(error) : resolvePromise());
  });
  return port;
}

function delay(milliseconds) {
  return new Promise((resolvePromise) => setTimeout(resolvePromise, milliseconds));
}

async function waitForHttp(url, child, label, timeoutMs = 60_000) {
  const deadline = Date.now() + timeoutMs;
  let lastError = "pas encore de réponse";
  while (Date.now() < deadline) {
    if (serviceErrors.has(child)) {
      throw new Error(`${label} : ${serviceErrors.get(child).message}`);
    }
    if (child.exitCode !== null || child.signalCode !== null) {
      throw new Error(`${label} s'est arrêté avant de répondre.`);
    }
    try {
      const response = await fetch(url, { signal: AbortSignal.timeout(3_000) });
      if (response.ok) return;
      lastError = `HTTP ${response.status}`;
    } catch (error) {
      lastError = error instanceof Error ? error.message : String(error);
    }
    await delay(300);
  }
  throw new Error(`${label} n'a pas répondu à temps (${lastError}).`);
}

function waitForExit(child, timeoutMs) {
  return new Promise((resolvePromise) => {
    if (child.exitCode !== null || child.signalCode !== null) {
      resolvePromise(true);
      return;
    }
    const onExit = () => {
      clearTimeout(timer);
      resolvePromise(true);
    };
    const timer = setTimeout(() => {
      child.off("exit", onExit);
      resolvePromise(false);
    }, timeoutMs);
    child.once("exit", onExit);
  });
}

async function stopService(child, label) {
  if (!child || child.exitCode !== null || child.signalCode !== null) return;
  const gracefulExit = waitForExit(child, 5_000);
  child.kill("SIGTERM");
  const stopped = await gracefulExit;
  if (!stopped) {
    const forcedExit = waitForExit(child, 5_000);
    child.kill();
    await forcedExit;
  }
  console.log(`${label} arrêté.`);
}

async function removeIsolatedDirectory(path) {
  const tempRoot = await realpath(tmpdir());
  const target = await realpath(path);
  const relative = target.slice(tempRoot.length);
  if (
    !relative.startsWith(sep)
    || !/^finflow-api-smoke-[a-z0-9]+$/i.test(relative.slice(sep.length))
  ) {
    throw new Error("Refus de supprimer un dossier qui n'est pas un smoke test temporaire.");
  }
  let lastError;
  for (let attempt = 0; attempt < 8; attempt += 1) {
    try {
      await rm(target, {
        recursive: true,
        force: true,
        maxRetries: 4,
        retryDelay: 300,
      });
      return;
    } catch (error) {
      lastError = error;
      if (attempt < 7) await delay(250 * (attempt + 1));
    }
  }
  throw lastError;
}

let isolatedDirectory;
let apiServer;
let frontendServer;
let failed = false;

try {
  if (!existsSync(viteCli) || !existsSync(playwrightCli)) {
    throw new Error("Les dépendances frontend manquent ; exécuter npm install dans frontend/.");
  }

  isolatedDirectory = await mkdtemp(join(tmpdir(), "finflow-api-smoke-"));
  const sqliteFile = join(isolatedDirectory, "finflow.sqlite3");
  const backendEnv = {
    ...process.env,
    DATABASE_URL: sqliteUrl(sqliteFile),
    DJANGO_SETTINGS_MODULE: "config.settings.dev",
    DJANGO_SECRET_KEY: randomBytes(48).toString("base64url"),
    DJANGO_ALLOWED_HOSTS: "127.0.0.1,localhost",
    MEDIA_ROOT: join(isolatedDirectory, "media"),
    EMAIL_BACKEND: "django.core.mail.backends.locmem.EmailBackend",
    PYTHONUTF8: "1",
  };

  console.log("Migrations de la base SQLite temporaire…");
  await runCommand(python, ["manage.py", "migrate", "--noinput"], { cwd: backendRoot, env: backendEnv }, "Les migrations");
  console.log("Création du jeu de démonstration simulé…");
  await runCommand(
    python,
    ["manage.py", "seed_demo", "--volume", "--count", "20"],
    { cwd: backendRoot, env: backendEnv },
    "Le seed de démonstration",
  );

  const apiPort = await freePort();
  let frontendPort = await freePort();
  while (frontendPort === apiPort) frontendPort = await freePort();
  const apiBaseUrl = `http://127.0.0.1:${apiPort}`;
  const frontendBaseUrl = `http://127.0.0.1:${frontendPort}`;

  apiServer = startService(
    python,
    ["manage.py", "runserver", `127.0.0.1:${apiPort}`, "--noreload"],
    { cwd: backendRoot, env: backendEnv },
    "Django",
  );
  await waitForHttp(`${apiBaseUrl}/api/v1/tenants/branding/?code=FIL01`, apiServer, "L'API Django");

  const frontendEnv = {
    ...process.env,
    VITE_API_TARGET: apiBaseUrl,
  };
  frontendServer = startService(
    process.execPath,
    [viteCli, "--host", "127.0.0.1", "--port", String(frontendPort), "--strictPort"],
    { cwd: frontendRoot, env: frontendEnv },
    "Vite",
  );
  await waitForHttp(`${frontendBaseUrl}/login`, frontendServer, "Le frontend Vite");

  const smokeEnv = {
    ...frontendEnv,
    FINFLOW_API_BASE_URL: frontendBaseUrl,
    FINFLOW_API_TEST_OUTPUT_DIR: join(isolatedDirectory, "playwright-results"),
    FINFLOW_SMOKE_USERNAME: process.env.FINFLOW_SMOKE_USERNAME || "fil01_admin",
    FINFLOW_SMOKE_PASSWORD: process.env.FINFLOW_SMOKE_PASSWORD || "FinFlow2026!",
    FINFLOW_GROUP_SMOKE_USERNAME: process.env.FINFLOW_GROUP_SMOKE_USERNAME || "group_admin",
    FINFLOW_GROUP_SMOKE_PASSWORD: process.env.FINFLOW_GROUP_SMOKE_PASSWORD || "FinFlow2026!",
  };
  await runCommand(
    process.execPath,
    [playwrightCli, "test", "--config=playwright.api.config.ts"],
    { cwd: frontendRoot, env: smokeEnv },
    "Le smoke test Playwright avec l'API",
  );
} catch (error) {
  failed = true;
  console.error(error instanceof Error ? error.message : error);
} finally {
  await stopService(frontendServer, "Vite").catch((error) => {
    failed = true;
    console.error(error instanceof Error ? error.message : error);
  });
  await stopService(apiServer, "Django").catch((error) => {
    failed = true;
    console.error(error instanceof Error ? error.message : error);
  });
  if (isolatedDirectory) {
    await removeIsolatedDirectory(isolatedDirectory).catch((error) => {
      failed = true;
      console.error(error instanceof Error ? error.message : error);
    });
    if (!failed) console.log("Base et artefacts temporaires supprimés.");
  }
}

if (failed) process.exitCode = 1;

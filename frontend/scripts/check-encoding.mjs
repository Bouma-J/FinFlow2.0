import { readdirSync, readFileSync } from "node:fs";
import { extname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { TextDecoder } from "node:util";

// Sans argument : frontend. Avec un chemin : contrôle du projet complet possible.
const root = resolve(process.argv[2] || fileURLToPath(new URL("..", import.meta.url)));
const excluded = new Set([
  ".git", ".venv", "venv", "node_modules", "dist", "__pycache__",
  ".pytest_cache", ".mypy_cache", ".ruff_cache", "htmlcov", "media", "staticfiles",
]);
const extensions = new Set([
  ".py", ".tsx", ".ts", ".js", ".jsx", ".mjs", ".cjs", ".css", ".scss",
  ".html", ".json", ".md", ".txt", ".csv", ".yml", ".yaml", ".toml",
  ".ini", ".cfg", ".conf", ".sh", ".ps1", ".bat", ".sql", ".xml", ".svg",
  ".env", ".example", ".properties",
]);
const filenames = new Set([".editorconfig", ".gitattributes", "Dockerfile", "Makefile"]);
// Séquences typiques d'un UTF-8 relu en Windows-1252/Latin-1, pas les accents valides.
const corrupted = /(?:\u00c3[\u0080-\u00bf\u0152\u0153\u0160\u0161\u0178\u017d\u017e\u20ac\u201a\u201e\u2026\u2020\u2021\u02c6\u2030\u2039\u203a\u02dc\u2018\u2019\u201c\u201d\u2022\u2013\u2014\u2122]|\u00c2[\u0080-\u00bf]|\u00e2[\u0080-\u00bf\u20ac\u201a\u201e\u2026\u2018\u2019\u201c\u201d]|\u00f0\u0178|\ufffd|[\u0080-\u009f])/u;
const decoder = new TextDecoder("utf-8", { fatal: true });
let scanned = 0;
let errors = 0;

function visit(directory) {
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) {
      if (!excluded.has(entry.name)) visit(path);
      continue;
    }
    if (!entry.isFile() || (!extensions.has(extname(entry.name).toLowerCase()) &&
        !filenames.has(entry.name) && !entry.name.startsWith(".env."))) continue;
    scanned += 1;
    let text;
    try {
      text = decoder.decode(readFileSync(path));
    } catch (error) {
      if (!(error instanceof TypeError)) throw error;
      console.error(`${relative(root, path)} : fichier non valide en UTF-8`);
      errors += 1;
      continue;
    }
    text.split(/\r?\n/).forEach((line, index) => {
      if (corrupted.test(line)) {
        // Ne pas afficher le contenu : un fichier peut contenir des données privées.
        console.error(`${relative(root, path)}:${index + 1} : séquence d'encodage suspecte`);
        errors += 1;
      }
    });
  }
}

visit(root);
if (errors) {
  console.error(`Encodage : ${errors} anomalie(s), ${scanned} fichiers contrôlés.`);
  process.exitCode = 1;
} else {
  console.log(`Encodage UTF-8 : ${scanned} fichiers contrôlés, aucune anomalie détectée.`);
}

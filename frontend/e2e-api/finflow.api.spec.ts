import { expect, test, type Page, type Response } from "@playwright/test";

const apiBasePath = "/api/v1";

function apiPath(response: Response) {
  return new URL(response.url()).pathname.replace(apiBasePath, "") || "/";
}

function isApiResponse(response: Response, path: string, method = "GET") {
  return apiPath(response) === path && response.request().method() === method;
}

async function openPage(page: Page, path: string) {
  await page.goto(path, { waitUntil: "domcontentloaded" });
}

async function switchSessionUser(page: Page, username: string, password: string) {
  await page.evaluate(() => {
    localStorage.clear();
    sessionStorage.clear();
  });
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page).toHaveURL(/\/login/);
  await page.getByPlaceholder("ex. FIL01").fill("FIL01");
  await page.getByPlaceholder("votre identifiant").fill(username);
  await page.getByPlaceholder("••••••••").fill(password);
  const loginResponse = page.waitForResponse((response) =>
    isApiResponse(response, "/auth/token/", "POST"),
  );
  await page.getByRole("button", { name: "Se connecter" }).click();
  expect((await loginResponse).status(), `connexion de ${username}`).toBe(200);
  await expect(page).not.toHaveURL(/\/login/);
}

async function loginDemoAdmin(page: Page) {
  const password = process.env.FINFLOW_SMOKE_PASSWORD;
  test.skip(!password, "Définir FINFLOW_SMOKE_PASSWORD pour lancer le smoke test API.");
  await openPage(page, "/login");
  await page.getByPlaceholder("ex. FIL01").fill("FIL01");
  await page.getByPlaceholder("votre identifiant").fill("fil01_admin");
  await page.getByPlaceholder("••••••••").fill(password!);
  const loginResponse = page.waitForResponse((response) =>
    isApiResponse(response, "/auth/token/", "POST"),
  );
  await page.getByRole("button", { name: "Se connecter" }).click();
  expect((await loginResponse).status(), "connexion de l'administrateur de recette").toBe(200);
  await expect(page).not.toHaveURL(/\/login/);
}

async function browserApiGet<T>(page: Page, path: string): Promise<T> {
  const result = await page.evaluate(async (apiPath) => {
    const access = localStorage.getItem("finflow_access");
    const tenant = localStorage.getItem("finflow_tenant");
    const headers: Record<string, string> = {};
    if (access) headers.Authorization = `Bearer ${access}`;
    if (tenant) headers["X-Tenant-Id"] = tenant;
    const response = await fetch(`/api/v1${apiPath}`, { headers });
    return { status: response.status, data: await response.json() as unknown };
  }, path);
  expect(result.status, `GET ${path}`).toBe(200);
  return result.data as T;
}

test("parcours métier sur l'API de recette isolée", async ({ page }) => {
  const password = process.env.FINFLOW_SMOKE_PASSWORD;
  test.skip(!password, "Définir FINFLOW_SMOKE_PASSWORD pour lancer le smoke test API.");

  const username = process.env.FINFLOW_SMOKE_USERNAME || "fil01_admin";
  const apiErrors: string[] = [];
  const pageErrors: string[] = [];
  page.on("response", (response) => {
    if (new URL(response.url()).pathname.startsWith(`${apiBasePath}/`) && response.status() >= 400) {
      apiErrors.push(`${response.request().method()} ${apiPath(response)} → ${response.status()}`);
    }
  });
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await openPage(page, "/login");
  await page.getByPlaceholder("ex. FIL01").fill("FIL01");
  await page.getByPlaceholder("votre identifiant").fill(username);
  await page.getByPlaceholder("••••••••").fill(password!);

  const loginResponse = page.waitForResponse((response) => isApiResponse(response, "/auth/token/", "POST"));
  await page.getByRole("button", { name: "Se connecter" }).click();
  expect((await loginResponse).status()).toBe(200);
  await expect(page).not.toHaveURL(/\/login/);

  const clientsResponse = page.waitForResponse((response) => isApiResponse(response, "/clients/"));
  await openPage(page, "/clients");
  expect((await clientsResponse).status()).toBe(200);
  await expect(page.getByRole("heading", { name: "Clients" })).toBeVisible();

  const searchResponse = page.waitForResponse((response) => {
    return isApiResponse(response, "/clients/")
      && new URL(response.url()).searchParams.get("search") === "CLI-0001";
  });
  await page.getByPlaceholder("Nom, référence, téléphone, pièce, CBS…").fill("CLI-0001");
  const searchedResponse = await searchResponse;
  expect(searchedResponse.status()).toBe(200);
  const searchedClients = await searchedResponse.json() as {
    results: Array<{ id: string; reference: string; display_name: string }>;
  };
  const demoClient = searchedClients.results.find((client) => client.reference === "CLI-0001");
  expect(demoClient, "le client de démonstration doit exister").toBeTruthy();

  await openPage(page, `/clients/${demoClient!.id}/modifier`);
  await expect(page.getByRole("heading", { name: "Modifier — Awa Koné" })).toBeVisible();
  await page.getByLabel("Ville", { exact: true }).fill("Ville intégration temporaire");
  const updateClientResponse = page.waitForResponse((response) =>
    isApiResponse(response, `/clients/${demoClient!.id}/`, "PATCH"),
  );
  const readBackClientResponse = page.waitForResponse((response) =>
    isApiResponse(response, `/clients/${demoClient!.id}/`),
  );
  await page.getByRole("button", { name: "Enregistrer les modifications" }).click();
  const updatedClient = await updateClientResponse;
  expect(updatedClient.status(), "la modification du client doit réussir").toBe(200);
  expect(await updatedClient.json()).toMatchObject({
    id: demoClient!.id, reference: "CLI-0001", city: "Ville intégration temporaire",
  });
  const persistedClient = await readBackClientResponse;
  expect(persistedClient.status(), "le client modifié doit être relisible").toBe(200);
  expect(await persistedClient.json()).toMatchObject({
    id: demoClient!.id, reference: "CLI-0001", city: "Ville intégration temporaire",
  });

  const moduleJourneys = [
    { link: "Dossiers de crédit", heading: "Dossiers de crédit", endpoint: "/credit-applications/" },
    { link: "Mes validations", heading: "Mes validations", endpoint: "/approval-tasks/my_dossiers/" },
    { link: "Prêts", heading: "Prêts", endpoint: "/loans/" },
    { link: "Garanties", heading: "Garanties", endpoint: "/guarantees/" },
    { link: "Recouvrement", heading: "Recouvrement", endpoint: "/collection-cases/" },
    { link: "GED", heading: "GED — Documents", endpoint: "/documents/" },
  ] as const;

  for (const journey of moduleJourneys) {
    const response = page.waitForResponse((item) => isApiResponse(item, journey.endpoint));
    await page.getByRole("link", { name: journey.link, exact: true }).click();
    await expect(page.getByRole("heading", { name: journey.heading, exact: true })).toBeVisible();
    expect((await response).status(), `${journey.endpoint} doit répondre 200`).toBe(200);
  }

  const catalogueResponse = page.waitForResponse((response) =>
    isApiResponse(response, "/configuration-profiles/catalogue/"),
  );
  const profilesResponse = page.waitForResponse((response) =>
    isApiResponse(response, "/configuration-profiles/"),
  );
  await openPage(page, "/admin/configuration");
  await expect(page.getByRole("heading", { name: "Centre de configuration" })).toBeVisible();
  expect((await catalogueResponse).status()).toBe(200);
  expect((await profilesResponse).status()).toBe(200);

  const contextResponse = page.waitForResponse((response) =>
    isApiResponse(response, "/credit-applications/configuration-context/"),
  );
  await openPage(page, "/dossiers/nouveau");
  await expect(page.getByRole("heading", { name: "Nouveau dossier de crédit" })).toBeVisible();
  const clientLookup = page.waitForResponse((response) => {
    return isApiResponse(response, "/clients/")
      && new URL(response.url()).searchParams.get("search") === "CLI-0001";
  });
  await page.getByPlaceholder("Matricule Core Banking, nom, dénomination ou référence…").fill("CLI-0001");
  expect((await clientLookup).status()).toBe(200);
  await page.getByRole("button", { name: /Awa Koné/ }).click();
  const product = page.getByLabel("Type de crédit");
  await expect(product.locator("option").nth(1)).toBeAttached();
  await product.selectOption({ index: 1 });
  expect((await contextResponse).status()).toBe(200);

  await page.getByLabel("Montant demandé").fill("250000");
  await page.getByLabel("Durée du crédit (mois)").fill("12");
  const createResponse = page.waitForResponse((response) =>
    isApiResponse(response, "/credit-applications/", "POST"),
  );
  await page.getByRole("button", { name: "Enregistrer le dossier" }).click();
  const createdResponse = await createResponse;
  expect(createdResponse.status(), "le brouillon doit être enregistré en base").toBe(201);
  const createdApplication = await createdResponse.json() as {
    id: string;
    reference: string;
    client: string;
    product: string;
    amount_requested: string;
    status: string;
  };
  expect(createdApplication.id).toBeTruthy();
  expect(createdApplication.reference).toBeTruthy();
  expect(createdApplication.client).toBeTruthy();
  expect(createdApplication.product).toBeTruthy();
  expect(createdApplication.amount_requested).toBe("250000.00");
  expect(createdApplication.status).toBe("DRAFT");

  const readBackResponse = page.waitForResponse((response) =>
    isApiResponse(response, `/credit-applications/${createdApplication.id}/`),
  );
  await openPage(page, `/dossiers/${createdApplication.id}`);
  const persistedResponse = await readBackResponse;
  expect(persistedResponse.status(), "le dossier relu doit exister").toBe(200);
  const persistedApplication = await persistedResponse.json();
  expect(persistedApplication).toMatchObject({
    id: createdApplication.id,
    reference: createdApplication.reference,
    client: createdApplication.client,
    product: createdApplication.product,
    amount_requested: "250000.00",
    status: "DRAFT",
  });
  const readinessSection = page.locator("#sec-readiness");
  await expect(readinessSection.locator(".form-section-title")).toHaveText("Préparation à la soumission");
  await readinessSection.locator(".form-section-head").click();
  await expect(readinessSection.getByText("Analyse financière de référence avec recommandation")).toBeVisible();
  await expect(page.getByRole("button", { name: "Soumettre à validation" })).toBeDisabled();

  const guaranteeNumber = `TF-API-E2E-${Date.now()}`;
  await openPage(page, `/dossiers/${createdApplication.id}/garanties/nouvelle`);
  await expect(page.getByRole("heading", { name: "Ajouter une garantie" })).toBeVisible();
  await page.getByLabel("Type de document").selectOption("LAND_TITLE");
  await page.getByLabel("Numéro du document").fill(guaranteeNumber);
  await page.getByLabel("Date d'établissement").fill("2026-10-25");
  await page.getByLabel("Valeur expertisée (XOF)").fill("250000");
  await page.getByLabel("Date de l'expertise").fill("2026-10-25");
  await page.getByLabel("Nom de l'expert").fill("Expert intégration");

  const createGuaranteeResponse = page.waitForResponse((response) =>
    isApiResponse(response, "/guarantees/", "POST"),
  );
  const guaranteeListResponse = page.waitForResponse((response) =>
    isApiResponse(response, "/guarantees/")
      && new URL(response.url()).searchParams.get("application") === createdApplication.id,
  );
  await page.getByRole("button", { name: "Enregistrer la garantie" }).click();
  const createdGuaranteeResponse = await createGuaranteeResponse;
  expect(createdGuaranteeResponse.status(), "la garantie doit être enregistrée").toBe(201);
  const createdGuarantee = await createdGuaranteeResponse.json() as {
    id: string;
    guarantee_type: string;
    application: string;
    client: string;
    document_number: string;
    expertise_value: string;
  };
  expect(createdGuarantee).toMatchObject({
    guarantee_type: "MORTGAGE",
    application: createdApplication.id,
    client: createdApplication.client,
    document_number: guaranteeNumber,
    expertise_value: "250000.00",
  });
  const listedGuarantees = await guaranteeListResponse;
  expect(listedGuarantees.status(), "la garantie doit réapparaître sur le dossier").toBe(200);
  const guaranteeList = await listedGuarantees.json() as {
    results: Array<{ id: string; application: string }>;
  };
  expect(guaranteeList.results).toContainEqual(expect.objectContaining({
    id: createdGuarantee.id,
    application: createdApplication.id,
  }));

  await openPage(page, `/dossiers/${createdApplication.id}/analyse-financiere`);
  await expect(page.getByRole("heading", { name: "Nouvelle analyse financière" })).toBeVisible();
  await page.getByLabel("Date de l'analyse").fill("2026-10-25");
  await page.getByLabel("Salaire net (demandeur)").fill("400000");
  await page.getByLabel("Recommandation (obligatoire pour soumettre)").selectOption("FAVORABLE");

  const createAnalysisResponse = page.waitForResponse((response) =>
    isApiResponse(response, "/financial-analyses/", "POST"),
  );
  const readyAfterAnalysisResponse = page.waitForResponse((response) =>
    isApiResponse(response, `/credit-applications/${createdApplication.id}/readiness/`),
  );
  await page.getByRole("button", { name: "Enregistrer l'analyse" }).click();
  const createdAnalysisResponse = await createAnalysisResponse;
  expect(createdAnalysisResponse.status(), "l'analyse doit être enregistrée").toBe(201);
  const createdAnalysis = await createdAnalysisResponse.json() as {
    id: string;
    application: string;
    recommendation: string;
    salary_income: string;
  };
  expect(createdAnalysis).toMatchObject({
    application: createdApplication.id,
    recommendation: "FAVORABLE",
    salary_income: "400000.00",
  });
  const readyAfterAnalysis = await readyAfterAnalysisResponse;
  expect(readyAfterAnalysis.status(), "les contrôles de readiness doivent se recalculer").toBe(200);
  const readiness = await readyAfterAnalysis.json() as {
    ready: boolean;
    checks: Array<{ key: string; label: string; ok: boolean; blocking: boolean; message: string }>;
  };
  const blockingFailures = readiness.checks
    .filter((check) => check.blocking && !check.ok)
    .map((check) => `${check.key}: ${check.message || check.label}`);
  expect(readiness.ready, `le dossier doit être prêt à soumettre : ${blockingFailures.join(" | ")}`).toBe(true);

  await expect(page).toHaveURL(new RegExp(`/dossiers/${createdApplication.id}$`));
  const readySection = page.locator("#sec-readiness");
  await expect(readySection.locator(".form-section-title")).toHaveText("Préparation à la soumission");
  await readySection.locator(".form-section-head").click();
  await expect(readySection.getByText("Le dossier peut être soumis au circuit.")).toBeVisible();
  const workflowResponse = page.waitForResponse((response) => {
    return isApiResponse(response, "/workflow-instances/")
      && new URL(response.url()).searchParams.get("object_id") === createdApplication.id;
  });
  const submitResponse = page.waitForResponse((response) =>
    isApiResponse(response, `/credit-applications/${createdApplication.id}/submit/`, "POST"),
  );
  await page.getByRole("button", { name: "Soumettre à validation" }).click();
  const submittedApplication = await submitResponse;
  expect(submittedApplication.status(), "la soumission au circuit doit réussir").toBe(200);
  expect(await submittedApplication.json()).toMatchObject({
    id: createdApplication.id,
    status: "IN_APPROVAL",
  });
  const workflowCreated = await workflowResponse;
  expect(workflowCreated.status(), "le circuit d'approbation doit être relisible").toBe(200);
  const workflow = await workflowCreated.json() as {
    results: Array<{
      status: string;
      tasks: Array<{ id: string; status: string; step_kind: string; step_order: number }>;
    }>;
  };
  expect(workflow.results).toHaveLength(1);
  expect(workflow.results[0]).toMatchObject({ status: "IN_PROGRESS" });
  const consultantTask = workflow.results[0].tasks.find((task) => task.status === "PENDING" && task.step_order === 1);
  expect(consultantTask?.step_kind).toBe("CONSULTATIVE");

  const simulationResponse = page.waitForResponse((response) =>
    isApiResponse(response, "/credit-applications/simulate/", "POST"),
  );
  await openPage(page, "/simulateur");
  await expect(page.getByRole("heading", { name: "Simulateur d'amortissement" })).toBeVisible();
  await page.getByRole("button", { name: "Simuler l'échéancier" }).click();
  expect((await simulationResponse).status()).toBe(200);
  await expect(page.getByText("Nombre d'échéances")).toBeVisible();

  await switchSessionUser(page, "fil01_analyste", password!);
  const analystQueueResponse = page.waitForResponse((response) =>
    isApiResponse(response, "/approval-tasks/my_dossiers/")
      && new URL(response.url()).searchParams.get("queue") === "actionable",
  );
  await openPage(page, "/taches");
  const analystQueue = await analystQueueResponse;
  expect(analystQueue.status(), "la file de l'analyste doit charger").toBe(200);
  const analystRows = await analystQueue.json() as {
    results: Array<{ id: string; reference: string; is_actionable: boolean; my_step_order: number | null }>;
  };
  const analystRow = analystRows.results.find((row) => row.id === createdApplication.id);
  expect(analystRow, "le dossier doit apparaître dans la file de l'analyste").toMatchObject({
    reference: createdApplication.reference,
    is_actionable: true,
    my_step_order: 1,
  });
  await page.locator(".valid-card").filter({ hasText: createdApplication.reference }).click();
  await expect(page.getByRole("button", { name: "Décision à rendre" })).toBeVisible();
  await page.getByRole("button", { name: "Décision à rendre" }).click();
  await page.getByLabel("Favorable", { exact: true }).check();
  const analystDecisionResponse = page.waitForResponse((response) =>
    isApiResponse(response, `/approval-tasks/${consultantTask!.id}/decide/`, "POST"),
  );
  await page.getByRole("button", { name: "Valider et transmettre" }).click();
  const analystDecision = await analystDecisionResponse;
  expect(analystDecision.status(), "l'avis consultatif de l'analyste doit être transmis").toBe(200);
  const updatedWorkflow = await analystDecision.json() as {
    status: string;
    current_order: number;
    tasks: Array<{ id: string; status: string; step_order: number; step_kind: string }>;
  };
  const managerTask = updatedWorkflow.tasks.find((task) =>
    task.status === "PENDING" && task.step_kind === "DECISIONAL" && task.step_order === updatedWorkflow.current_order,
  );
  expect(managerTask, `une étape décisionnelle doit prendre le relais : ${JSON.stringify(updatedWorkflow)}`).toBeTruthy();

  await switchSessionUser(page, "fil01_chef", password!);
  const managerQueueResponse = page.waitForResponse((response) =>
    isApiResponse(response, "/approval-tasks/my_dossiers/")
      && new URL(response.url()).searchParams.get("queue") === "actionable",
  );
  await openPage(page, "/taches");
  const managerQueue = await managerQueueResponse;
  expect(managerQueue.status(), "la file du chef d'agence doit charger").toBe(200);
  const managerRows = await managerQueue.json() as {
    results: Array<{ id: string; reference: string; is_actionable: boolean; my_step_order: number | null }>;
  };
  const managerRow = managerRows.results.find((row) => row.id === createdApplication.id);
  expect(managerRow, "le dossier doit apparaître dans la file du chef d'agence").toMatchObject({
    reference: createdApplication.reference,
    is_actionable: true,
    my_step_order: managerTask!.step_order,
  });
  await page.locator(".valid-card").filter({ hasText: createdApplication.reference }).click();
  await expect(page.getByRole("button", { name: "Décision à rendre" })).toBeVisible();
  await page.getByRole("button", { name: "Décision à rendre" }).click();
  await page.getByLabel("Favorable", { exact: true }).check();
  const managerDecisionResponse = page.waitForResponse((response) =>
    isApiResponse(response, `/approval-tasks/${managerTask!.id}/decide/`, "POST"),
  );
  const finalApplicationResponse = page.waitForResponse((response) =>
    isApiResponse(response, `/credit-applications/${createdApplication.id}/`),
  );
  await page.getByRole("button", { name: "Valider et transmettre" }).click();
  const managerDecision = await managerDecisionResponse;
  expect(managerDecision.status(), "la décision d'agence doit réussir").toBe(200);
  const approvedWorkflow = await managerDecision.json() as {
    status: string;
    tasks: Array<{ status: string; step_order: number }>;
  };
  expect(approvedWorkflow.status).toBe("APPROVED");
  expect(approvedWorkflow.tasks.every((task) => task.status === "APPROVED")).toBe(true);
  const finalApplication = await finalApplicationResponse;
  expect(await finalApplication.json()).toMatchObject({
    id: createdApplication.id,
    status: "APPROVED",
  });

  await switchSessionUser(page, "fil01_admin", password!);
  const formalizationContext = page.waitForResponse((response) =>
    isApiResponse(response, "/guarantee-formalizations/compose-context/"),
  );
  await openPage(page, `/formalisations/nouvelle?client=${createdApplication.client}&application=${createdApplication.id}&guarantee=${createdGuarantee.id}`);
  expect((await formalizationContext).status(), "les garanties du dossier doivent être proposées à la formalisation").toBe(200);
  await expect(page.getByRole("heading", { name: "Nouvelle formalisation" })).toBeVisible();
  await page.getByLabel("Notaire / étude").fill("Étude de recette");
  await page.getByLabel("Réf. dossier notaire").fill("NOT-E2E-001");
  await page.getByLabel("Commentaire").fill("Formalisation interactive de la garantie créée dans le parcours.");
  const createFormalization = page.waitForResponse((response) =>
    isApiResponse(response, "/guarantee-formalizations/", "POST"),
  );
  await page.getByRole("button", { name: "Mettre dans le circuit" }).click();
  const createFormalizationResponse = await createFormalization;
  expect(createFormalizationResponse.status(), "le brouillon de formalisation doit être enregistré").toBe(201);
  const formalization = await createFormalizationResponse.json() as {
    id: string; guarantee: string; status: string;
  };
  expect(formalization).toMatchObject({ guarantee: createdGuarantee.id, status: "DRAFT" });
  await expect(page).toHaveURL(new RegExp(`/formalisations/${formalization.id}$`));

  const startFormalization = page.waitForResponse((response) =>
    isApiResponse(response, `/guarantee-formalizations/${formalization.id}/start/`, "POST"),
  );
  await page.getByRole("button", { name: "Démarrer" }).click();
  expect((await startFormalization).status(), "la formalisation doit passer au suivi juridique").toBe(200);
  const submitFormalization = page.waitForResponse((response) =>
    isApiResponse(response, `/guarantee-formalizations/${formalization.id}/submit/`, "POST"),
  );
  await page.getByRole("button", { name: "Soumettre au circuit" }).click();
  const submittedFormalization = await submitFormalization;
  expect(submittedFormalization.status(), "la formalisation doit rejoindre son circuit de validation").toBe(200);
  expect(await submittedFormalization.json()).toMatchObject({ id: formalization.id, status: "IN_APPROVAL" });

  expect(apiErrors, "réponses API en erreur").toEqual([]);
  expect(pageErrors, "erreurs JavaScript du navigateur").toEqual([]);
});

test("écrans de modules accessibles à l'administrateur de groupe", async ({ page }) => {
  const username = process.env.FINFLOW_GROUP_SMOKE_USERNAME;
  const password = process.env.FINFLOW_GROUP_SMOKE_PASSWORD;
  test.skip(!username || !password, "Définir les identifiants de recette groupe pour auditer les modules.");

  const apiErrors: string[] = [];
  const pageErrors: string[] = [];
  page.on("response", (response) => {
    if (new URL(response.url()).pathname.startsWith(`${apiBasePath}/`) && response.status() >= 400) {
      apiErrors.push(`${response.request().method()} ${apiPath(response)} → ${response.status()}`);
    }
  });
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await openPage(page, "/login");
  await page.getByPlaceholder("ex. FIL01").fill("FIL01");
  await page.getByPlaceholder("votre identifiant").fill(username!);
  await page.getByPlaceholder("••••••••").fill(password!);
  const loginResponse = page.waitForResponse((response) => isApiResponse(response, "/auth/token/", "POST"));
  await page.getByRole("button", { name: "Se connecter" }).click();
  expect((await loginResponse).status()).toBe(200);

  const readOnlyModuleRoutes = [
    "/",
    "/profil",
    "/clients",
    "/dossiers",
    "/prets",
    "/taches",
    "/cautions",
    "/garanties",
    "/mains-levees",
    "/dations",
    "/formalisations",
    "/documents",
    "/recouvrement",
    "/admin/filiales",
    "/admin/consolidation",
    "/admin/agences",
    "/admin/utilisateurs",
    "/admin/roles",
    "/admin/produits",
    "/admin/referentiels-metier",
    "/admin/intervenants-juridiques",
    "/admin/circuits",
    "/admin/delegations",
    "/admin/contrats",
    "/admin/connecteurs",
    "/admin/alertes",
    "/admin/politique-credit",
    "/admin/configuration",
    "/admin/tranches-recouvrement",
    "/admin/regles-escalade",
    "/admin/audit",
    // These legacy/secondary routes have no sidebar entry, so use a full navigation last.
    "/produits",
    "/apres-vente",
  ];
  const moduleIssues: string[] = [];
  const sidebarToggle = page.locator(".sidebar-toggle.desktop-only");
  if (await sidebarToggle.getAttribute("aria-label") === "Déployer le menu") {
    await sidebarToggle.click();
  }
  for (const toggle of await page.locator(".sidebar .nav-group-toggle").all()) {
    if (await toggle.isVisible() && await toggle.getAttribute("aria-expanded") === "false") {
      await toggle.click();
    }
  }
  for (const route of readOnlyModuleRoutes) {
    const routeApiErrorStart = apiErrors.length;
    const routePageErrorStart = pageErrors.length;
    if (route === "/profil") {
      await page.locator(".user-chip").click();
      await page.getByRole("menuitem", { name: "Mon profil" }).click();
    } else {
      const link = page.locator(`.sidebar a.nav-link[href="${route}"]`).first();
      if (await link.count() === 0) {
        // Some routes are legacy entry points or are reached from another module, not the sidebar.
        await openPage(page, route);
      } else {
        await link.click();
      }
    }
    await expect(page).toHaveURL((url) => url.pathname === route);
    const main = page.locator("main");
    try {
      await expect(main).toBeVisible({ timeout: 5_000 });
      await expect(main).toContainText(/\S/, { timeout: 5_000 });
      await page.waitForLoadState("networkidle", { timeout: 5_000 }).catch(() => undefined);
    } catch {
      moduleIssues.push(`${route}: écran principal absent ou vide`);
      continue;
    }
    const routeApiErrors = apiErrors.slice(routeApiErrorStart);
    const routePageErrors = pageErrors.slice(routePageErrorStart);
    if (routeApiErrors.length > 0) moduleIssues.push(`${route}: ${routeApiErrors.join(", ")}`);
    if (routePageErrors.length > 0) moduleIssues.push(`${route}: JavaScript ${routePageErrors.join(", ")}`);
  }

  expect(
    moduleIssues,
    `écrans ou API en erreur pendant le parcours des modules: ${moduleIssues.join(" | ")}`,
  ).toEqual([]);
  expect(apiErrors, "réponses API en erreur").toEqual([]);
  expect(pageErrors, "erreurs JavaScript du navigateur").toEqual([]);
});

test("publication réelle d'une configuration et application au prochain dossier", async ({ page }) => {
  const groupUsername = process.env.FINFLOW_GROUP_SMOKE_USERNAME;
  const password = process.env.FINFLOW_GROUP_SMOKE_PASSWORD;
  test.skip(!groupUsername || !password, "Définir les identifiants de recette groupe pour auditer la publication.");

  const apiErrors: string[] = [];
  const pageErrors: string[] = [];
  page.on("response", (response) => {
    if (new URL(response.url()).pathname.startsWith(`${apiBasePath}/`) && response.status() >= 400) {
      apiErrors.push(`${response.request().method()} ${apiPath(response)} → ${response.status()}`);
    }
  });
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await openPage(page, "/login");
  await page.getByPlaceholder("ex. FIL01").fill("FIL01");
  await page.getByPlaceholder("votre identifiant").fill(groupUsername!);
  await page.getByPlaceholder("••••••••").fill(password!);
  const groupLogin = page.waitForResponse((response) => isApiResponse(response, "/auth/token/", "POST"));
  await page.getByRole("button", { name: "Se connecter" }).click();
  expect((await groupLogin).status()).toBe(200);
  await expect(page).not.toHaveURL(/\/login/);

  const tenantSwitcher = page.locator(".tenant-switcher");
  await expect(tenantSwitcher).toBeVisible();
  const fil01Option = tenantSwitcher.locator("option").filter({ hasText: "FIL01 —" });
  const tenantId = await fil01Option.getAttribute("value");
  expect(tenantId, "la filiale de recette doit être sélectionnable").toBeTruthy();
  await tenantSwitcher.selectOption(tenantId!);

  const profileCode = `e2e-config-${Date.now()}`;
  await openPage(page, "/admin/configuration");
  await expect(page.getByRole("heading", { name: "Centre de configuration" })).toBeVisible();
  await page.getByRole("button", { name: "Nouveau profil" }).click();
  await page.getByLabel("Code stable").fill(profileCode);
  await page.getByLabel("Intitulé").fill("Profil de recette intégration");
  await page.getByLabel("Motif de modification").fill("Vérification du cycle réel de publication et de son application.");
  await page.getByLabel(/Mois de relevés examinés/).fill("6");
  await page.getByRole("checkbox", { name: "Validité de l'accord" }).check();
  const approvalValidity = page.locator(".field").filter({ hasText: "Validité de l'accord" }).locator('input[type="number"]');
  await approvalValidity.fill("60");

  const createProfile = page.waitForResponse((response) =>
    isApiResponse(response, "/configuration-profiles/", "POST"),
  );
  await page.getByRole("button", { name: "Enregistrer le brouillon" }).click();
  const createProfileResponse = await createProfile;
  expect(createProfileResponse.status(), "le profil doit être créé par l'interface").toBe(201);
  const createdProfile = await createProfileResponse.json() as { id: string; code: string; status: string };
  expect(createdProfile).toMatchObject({ code: profileCode, status: "DRAFT" });

  const preview = page.waitForResponse((response) =>
    isApiResponse(response, `/configuration-profiles/${createdProfile.id}/preview/`, "POST"),
  );
  await page.getByRole("button", { name: "Simuler le profil enregistré" }).click();
  const previewResponse = await preview;
  expect(previewResponse.status(), "l'aperçu doit résoudre les valeurs de la règle").toBe(200);
  const previewBody = await previewResponse.json() as {
    after: {
      analysis: { minimum_bank_statement_months: number };
      policy: { approval_validity_days: number };
      sources: Array<{ code: string }>;
    };
  };
  expect(previewBody.after.analysis.minimum_bank_statement_months).toBe(6);
  expect(previewBody.after.policy.approval_validity_days).toBe(60);
  expect(previewBody.after.sources.map((source) => source.code)).toContain(profileCode);

  const submitProfile = page.waitForResponse((response) =>
    isApiResponse(response, `/configuration-profiles/${createdProfile.id}/submit/`, "POST"),
  );
  await page.getByRole("button", { name: "Soumettre à validation" }).click();
  expect((await submitProfile).status(), "la soumission à validation doit réussir").toBe(200);
  await expect(page.locator(".card-title").filter({ hasText: "Profil de recette intégration — v1 — À valider" })).toBeVisible();

  await switchSessionUser(page, "fil01_admin", password!);
  await openPage(page, "/admin/configuration");
  const profileRow = page.getByRole("row").filter({ hasText: profileCode });
  await expect(profileRow).toBeVisible();
  await profileRow.getByRole("button", { name: "Ouvrir" }).click();
  const publishProfile = page.waitForResponse((response) =>
    isApiResponse(response, `/configuration-profiles/${createdProfile.id}/publish/`, "POST"),
  );
  await page.getByRole("button", { name: "Publier" }).click();
  const publishResponse = await publishProfile;
  expect(publishResponse.status(), "un second acteur habilité doit pouvoir publier le profil").toBe(200);
  expect(await publishResponse.json()).toMatchObject({ id: createdProfile.id, status: "PUBLISHED" });

  const clientLookup = page.waitForResponse((response) => {
    return isApiResponse(response, "/clients/")
      && new URL(response.url()).searchParams.get("search") === "CLI-0001";
  });
  await openPage(page, "/dossiers/nouveau");
  await page.getByPlaceholder("Matricule Core Banking, nom, dénomination ou référence…").fill("CLI-0001");
  expect((await clientLookup).status()).toBe(200);
  await page.getByRole("button", { name: /Awa Koné/ }).click();
  const product = page.getByLabel("Type de crédit");
  const applicationConfiguration = page.waitForResponse((response) =>
    isApiResponse(response, "/credit-applications/configuration-context/"),
  );
  await product.selectOption({ label: "Trésorerie standard" });
  expect((await applicationConfiguration).status(), "les exigences applicables doivent être chargées avant l'enregistrement").toBe(200);
  await page.getByLabel("Montant demandé").fill("250000");
  await page.getByLabel("Durée du crédit (mois)").fill("12");
  const createApplication = page.waitForResponse((response) =>
    isApiResponse(response, "/credit-applications/", "POST"),
  );
  await page.getByRole("button", { name: "Enregistrer le dossier" }).click();
  const applicationResponse = await createApplication;
  expect(applicationResponse.status()).toBe(201);
  const application = await applicationResponse.json() as { id: string; status: string };
  expect(application.status).toBe("DRAFT");

  const readiness = page.waitForResponse((response) =>
    isApiResponse(response, `/credit-applications/${application.id}/readiness/`),
  );
  await openPage(page, `/dossiers/${application.id}`);
  const readinessResponse = await readiness;
  expect(readinessResponse.status()).toBe(200);
  const readinessBody = await readinessResponse.json() as {
    configuration: {
      analysis: { minimum_bank_statement_months: number };
      policy: { approval_validity_days: number };
      sources: Array<{ code: string }>;
    };
  };
  expect(readinessBody.configuration.analysis.minimum_bank_statement_months).toBe(6);
  expect(readinessBody.configuration.policy.approval_validity_days).toBe(60);
  expect(readinessBody.configuration.sources.map((source) => source.code)).toContain(profileCode);

  await openPage(page, `/dossiers/${application.id}/cautions/nouvelle`);
  await page.getByRole("button", { name: "Créer une nouvelle caution" }).click();
  const suretyName = `Caution E2E ${Date.now()}`;
  await page.getByRole("textbox", { name: "Nom *", exact: true }).fill(suretyName);
  await page.getByLabel("Prénom", { exact: true }).fill("Solidaire");
  await page.getByLabel("Plafond (XOF)").fill("200000");
  const createSurety = page.waitForResponse((response) =>
    isApiResponse(response, "/sureties/", "POST"),
  );
  await page.getByRole("button", { name: "Enregistrer la caution" }).click();
  const createSuretyResponse = await createSurety;
  expect(createSuretyResponse.status(), "la caution doit être créée par l'interface").toBe(201);
  const surety = await createSuretyResponse.json() as { id: string; display_name: string; commitment_ceiling: string };
  expect(surety.display_name).toContain(suretyName);
  expect(surety.commitment_ceiling).toBe("200000.00");

  await page.getByLabel("Montant engagé (XOF)").fill("100000");
  const createEngagement = page.waitForResponse((response) =>
    isApiResponse(response, "/surety-engagements/", "POST"),
  );
  await page.getByRole("button", { name: "Rattacher la caution" }).click();
  const engagementResponse = await createEngagement;
  expect(engagementResponse.status(), "l'engagement doit être rattaché au dossier").toBe(201);
  expect(await engagementResponse.json()).toMatchObject({
    application: application.id,
    surety: surety.id,
    amount: "100000.00",
    engagement_type: "SOLIDAIRE",
  });

  expect(apiErrors, "réponses API en erreur").toEqual([]);
  expect(pageErrors, "erreurs JavaScript du navigateur").toEqual([]);
});

test("suivi de recouvrement : action de relance et promesse enregistrées", async ({ page }) => {
  const password = process.env.FINFLOW_SMOKE_PASSWORD;
  test.skip(!password, "Définir FINFLOW_SMOKE_PASSWORD pour lancer le smoke test API.");

  const apiErrors: string[] = [];
  const pageErrors: string[] = [];
  page.on("response", (response) => {
    if (new URL(response.url()).pathname.startsWith(`${apiBasePath}/`) && response.status() >= 400) {
      apiErrors.push(`${response.request().method()} ${apiPath(response)} → ${response.status()}`);
    }
  });
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await openPage(page, "/login");
  await page.getByPlaceholder("ex. FIL01").fill("FIL01");
  await page.getByPlaceholder("votre identifiant").fill("fil01_admin");
  await page.getByPlaceholder("••••••••").fill(password!);
  const loginResponse = page.waitForResponse((response) => isApiResponse(response, "/auth/token/", "POST"));
  await page.getByRole("button", { name: "Se connecter" }).click();
  expect((await loginResponse).status()).toBe(200);

  const casesResponse = page.waitForResponse((response) => isApiResponse(response, "/collection-cases/"));
  await openPage(page, "/recouvrement");
  expect((await casesResponse).status(), "la liste de recouvrement doit charger").toBe(200);
  await expect(page.getByRole("heading", { name: "Recouvrement", exact: true })).toBeVisible();
  const casesBody = await (await casesResponse).json() as {
    results: Array<{ id: string; application_reference: string; can_operate: boolean }>;
  };
  const operableCase = casesBody.results.find((item) => item.can_operate && item.application_reference);
  expect(operableCase, "un dossier de démonstration doit être accessible à l'administrateur").toBeTruthy();

  const caseDetailResponse = page.waitForResponse((response) =>
    isApiResponse(response, `/collection-cases/${operableCase!.id}/`),
  );
  await page.locator(".list-table-region tbody tr").filter({ hasText: operableCase!.application_reference }).click();
  expect((await caseDetailResponse).status(), "le détail du dossier de recouvrement doit charger").toBe(200);
  const actionsCard = page.locator(".card").filter({
    has: page.locator(".card-title", { hasText: "Historique des actions" }),
  });
  const actionDate = new Date().toISOString().slice(0, 10);
  const followUpDate = new Date(Date.now() + 2 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
  const actionResult = `Contact E2E ${Date.now()}`;
  await actionsCard.getByLabel("Date", { exact: true }).fill(actionDate);
  await actionsCard.getByLabel("Résultat", { exact: true }).fill(actionResult);
  await actionsCard.getByLabel("Suivi prévu", { exact: true }).fill(followUpDate);
  await actionsCard.getByLabel("Commentaire", { exact: true }).fill("Relance interactive depuis le dossier de recette.");
  const createAction = page.waitForResponse((response) => isApiResponse(response, "/collection-actions/", "POST"));
  await actionsCard.getByRole("button", { name: "Ajouter l'action" }).click();
  const actionResponse = await createAction;
  expect(actionResponse.status(), "l'action de relance doit être enregistrée").toBe(201);
  const createdAction = await actionResponse.json() as {
    id: string; case: string; action_type: string; result: string; next_follow_up_date: string;
  };
  expect(createdAction).toMatchObject({
    case: operableCase!.id,
    action_type: "CALL",
    result: actionResult,
    next_follow_up_date: followUpDate,
  });

  const promisesCard = page.locator(".card").filter({
    has: page.locator(".card-title", { hasText: "Promesses de paiement" }),
  });
  await promisesCard.getByLabel("Montant", { exact: true }).fill("1000");
  await promisesCard.getByLabel("Date promise", { exact: true }).fill(followUpDate);
  const createPromise = page.waitForResponse((response) => isApiResponse(response, "/payment-promises/", "POST"));
  await promisesCard.getByRole("button", { name: "Enregistrer la promesse" }).click();
  const promiseResponse = await createPromise;
  expect(promiseResponse.status(), "la promesse de paiement doit être enregistrée").toBe(201);
  const createdPromise = await promiseResponse.json() as {
    id: string; case: string; amount: string; promised_date: string; status: string;
  };
  expect(createdPromise).toMatchObject({
    case: operableCase!.id,
    amount: "1000.00",
    promised_date: followUpDate,
    status: "PENDING",
  });

  await openPage(page, `/recouvrement/${operableCase!.id}`);
  const persistedBody = await browserApiGet<{
    actions: Array<{ id: string; result: string }>;
    promises: Array<{ id: string; amount: string }>;
    next_action_date: string;
  }>(page, `/collection-cases/${operableCase!.id}/`);
  expect(persistedBody.actions).toContainEqual(expect.objectContaining({ id: createdAction.id, result: actionResult }));
  expect(persistedBody.promises).toContainEqual(expect.objectContaining({ id: createdPromise.id, amount: "1000.00" }));
  expect(persistedBody.next_action_date).toBe(followUpDate);
  expect(apiErrors, "réponses API en erreur").toEqual([]);
  expect(pageErrors, "erreurs JavaScript du navigateur").toEqual([]);
});

test("GED : filtrer les pièces et enregistrer leur vérification documentaire", async ({ page }) => {
  const password = process.env.FINFLOW_SMOKE_PASSWORD;
  test.skip(!password, "Définir FINFLOW_SMOKE_PASSWORD pour lancer le smoke test API.");

  const apiErrors: string[] = [];
  const pageErrors: string[] = [];
  page.on("response", (response) => {
    if (new URL(response.url()).pathname.startsWith(`${apiBasePath}/`) && response.status() >= 400) {
      apiErrors.push(`${response.request().method()} ${apiPath(response)} → ${response.status()}`);
    }
  });
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await openPage(page, "/login");
  await page.getByPlaceholder("ex. FIL01").fill("FIL01");
  await page.getByPlaceholder("votre identifiant").fill("fil01_admin");
  await page.getByPlaceholder("••••••••").fill(password!);
  const loginResponse = page.waitForResponse((response) => isApiResponse(response, "/auth/token/", "POST"));
  await page.getByRole("button", { name: "Se connecter" }).click();
  expect((await loginResponse).status()).toBe(200);

  const documentsResponse = page.waitForResponse((response) => isApiResponse(response, "/documents/"));
  await openPage(page, "/documents");
  expect((await documentsResponse).status(), "la GED doit charger ses documents").toBe(200);
  await expect(page.getByRole("heading", { name: "GED — Documents" })).toBeVisible();
  const documents = await (await documentsResponse).json() as {
    results: Array<{ id: string; name: string; file_url: string | null; expiry_date: string | null; verification_status: string }>;
  };
  const pendingDocument = documents.results.find((document) =>
    document.verification_status === "PENDING"
    && Boolean(document.file_url)
    && (!document.expiry_date || document.expiry_date >= new Date().toISOString().slice(0, 10)),
  );
  expect(pendingDocument, "une pièce non expirée doit pouvoir être vérifiée").toBeTruthy();

  const documentRow = page.getByRole("row").filter({ hasText: pendingDocument!.name });
  await expect(documentRow).toBeVisible();
  const verificationComment = `Contrôle GED E2E ${Date.now()}`;
  await documentRow.getByLabel("Commentaire de vérification").fill(verificationComment);
  const verifyDocument = page.waitForResponse((response) =>
    isApiResponse(response, `/documents/${pendingDocument!.id}/verify/`, "POST"),
  );
  await documentRow.getByRole("button", { name: "Vérifier" }).click();
  const verifyResponse = await verifyDocument;
  expect(verifyResponse.status(), "la vérification de la pièce doit être enregistrée").toBe(200);
  expect(await verifyResponse.json()).toMatchObject({
    id: pendingDocument!.id,
    verification_status: "VERIFIED",
    verification_comment: verificationComment,
  });

  const refreshedDocuments = page.waitForResponse((response) => isApiResponse(response, "/documents/"));
  await page.reload({ waitUntil: "domcontentloaded" });
  const refreshedResponse = await refreshedDocuments;
  expect(refreshedResponse.status(), "la GED doit relire la pièce après rechargement").toBe(200);
  const refreshedBody = await refreshedResponse.json() as {
    results: Array<{ id: string; verification_status: string; verification_comment: string }>;
  };
  expect(refreshedBody.results).toContainEqual(expect.objectContaining({
    id: pendingDocument!.id,
    verification_status: "VERIFIED",
    verification_comment: verificationComment,
  }));
  await expect(documentRow.getByText("Vérifié", { exact: true })).toBeVisible();
  expect(apiErrors, "réponses API en erreur").toEqual([]);
  expect(pageErrors, "erreurs JavaScript du navigateur").toEqual([]);
});

test("RBAC : un profil lecteur consulte la GED sans pouvoir vérifier une pièce", async ({ page }) => {
  const password = process.env.FINFLOW_SMOKE_PASSWORD;
  test.skip(!password, "Définir FINFLOW_SMOKE_PASSWORD pour lancer le smoke test API.");

  await openPage(page, "/login");
  await page.getByPlaceholder("ex. FIL01").fill("FIL01");
  await page.getByPlaceholder("votre identifiant").fill("fil01_lecteur");
  await page.getByPlaceholder("••••••••").fill(password!);
  const loginResponse = page.waitForResponse((response) => isApiResponse(response, "/auth/token/", "POST"));
  await page.getByRole("button", { name: "Se connecter" }).click();
  const authenticated = await loginResponse;
  expect(authenticated.status(), "le profil lecteur doit pouvoir se connecter").toBe(200);
  const authBody = await authenticated.json() as { access: string };

  const documentsResponse = page.waitForResponse((response) => isApiResponse(response, "/documents/"));
  await openPage(page, "/documents");
  expect((await documentsResponse).status(), "le lecteur doit pouvoir consulter la GED").toBe(200);
  const documents = await (await documentsResponse).json() as {
    results: Array<{ id: string; verification_status: string }>;
  };
  const pendingDocument = documents.results.find((document) => document.verification_status === "PENDING");
  expect(pendingDocument, "le jeu de recette doit contenir une pièce en attente").toBeTruthy();
  await expect(page.getByLabel("Commentaire de vérification")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Vérifier" })).toHaveCount(0);

  const deniedWrite = await page.request.post(
    new URL(`/api/v1/documents/${pendingDocument!.id}/verify/`, page.url()).toString(),
    {
      headers: { Authorization: `Bearer ${authBody.access}` },
      data: { status: "VERIFIED", comment: "Tentative non autorisée du profil lecteur." },
    },
  );
  expect(deniedWrite.status(), "l'API doit refuser la vérification au profil lecteur").toBe(403);
});

test("main levée : création, dépôt de la demande, génération de l'acte et soumission", async ({ page }) => {
  await loginDemoAdmin(page);
  const apiErrors: string[] = [];
  const pageErrors: string[] = [];
  page.on("response", (response) => {
    if (new URL(response.url()).pathname.startsWith(`${apiBasePath}/`) && response.status() >= 400) {
      apiErrors.push(`${response.request().method()} ${apiPath(response)} → ${response.status()}`);
    }
  });
  page.on("pageerror", (error) => pageErrors.push(error.message));

  type ReleaseContext = {
    client_id: string;
    cbs_client_id: string;
    guarantees: Array<{
      id: string;
      application: string | null;
      status: string;
      process_busy: unknown;
    }>;
    credits: Array<{
      application_id: string;
      loan_id: string | null;
      cbs_loan_reference: string;
      cbs_settled: boolean | null;
    }>;
  };
  const guaranteeList = await browserApiGet<{
    results: Array<{
      id: string;
      client: string;
      application: string | null;
      status: string;
      process_busy: unknown;
    }>;
  }>(page, "/guarantees/?status=ACTIVE&page_size=200");
  const contextByClient = new Map<string, ReleaseContext>();
  let selected: {
    clientId: string;
    applicationId: string;
    guaranteeId: string;
  } | null = null;

  for (const guarantee of guaranteeList.results) {
    if (guarantee.status !== "ACTIVE" || guarantee.process_busy) continue;
    let context = contextByClient.get(guarantee.client);
    if (!context) {
      context = await browserApiGet<ReleaseContext>(
        page,
        `/guarantee-releases/client-context/?client=${encodeURIComponent(guarantee.client)}`,
      );
      contextByClient.set(guarantee.client, context);
    }
    const availableGuarantee = context.guarantees.find(
      (candidate) => candidate.id === guarantee.id && !candidate.process_busy,
    );
    if (!availableGuarantee || !context.cbs_client_id) continue;
    const credit = context.credits.find(
      (candidate) =>
        candidate.cbs_settled === true
        && Boolean(candidate.cbs_loan_reference)
        && (!availableGuarantee.application
          || candidate.application_id === availableGuarantee.application),
    );
    if (!credit) continue;
    selected = {
      clientId: guarantee.client,
      applicationId: credit.application_id,
      guaranteeId: guarantee.id,
    };
    break;
  }
  expect(selected, "la recette doit fournir une garantie active libre et un crédit soldé simulé").toBeTruthy();

  const contextResponse = page.waitForResponse((response) =>
    isApiResponse(response, "/guarantee-releases/client-context/")
      && new URL(response.url()).searchParams.get("client") === selected!.clientId,
  );
  await openPage(
    page,
    `/mains-levees/nouvelle?client=${selected!.clientId}&application=${selected!.applicationId}&guarantee=${selected!.guaranteeId}`,
  );
  expect((await contextResponse).status(), "le contexte de composition doit se charger").toBe(200);
  await expect(page.getByRole("heading", { name: "Nouvelle main levée" })).toBeVisible();
  const createResponsePromise = page.waitForResponse((response) =>
    isApiResponse(response, "/guarantee-releases/", "POST"),
  );
  await page.getByRole("button", { name: "Créer le brouillon" }).click();
  const createResponse = await createResponsePromise;
  expect(createResponse.status(), "le brouillon de main levée doit être créé").toBe(201);
  const created = await createResponse.json() as { id: string; status: string; has_client_demande: boolean };
  expect(created.id).toBeTruthy();
  expect(created.status).toBe("DRAFT");
  expect(created.has_client_demande).toBe(false);

  await page.getByLabel("Fichier demande").setInputFiles({
    name: "demande-client-e2e.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.4\n% recette isolée\n%%EOF\n"),
  });
  const uploadResponsePromise = page.waitForResponse((response) =>
    isApiResponse(response, `/guarantee-releases/${created.id}/documents/`, "POST"),
  );
  await page.getByRole("button", { name: "Charger la demande" }).click();
  const uploadResponse = await uploadResponsePromise;
  expect(uploadResponse.status(), "la demande client doit être jointe").toBe(201);

  const generateResponsePromise = page.waitForResponse((response) =>
    isApiResponse(response, `/guarantee-releases/${created.id}/generate-acte/`, "POST"),
  );
  await page.getByRole("button", { name: "Générer l'acte" }).click();
  const generateResponse = await generateResponsePromise;
  expect(generateResponse.status(), "l'acte doit être généré").toBe(200);
  expect(await generateResponse.json()).toMatchObject({
    id: created.id,
    has_generated_acte: true,
  });

  const submitResponsePromise = page.waitForResponse((response) =>
    isApiResponse(response, `/guarantee-releases/${created.id}/submit/`, "POST"),
  );
  await page.getByRole("button", { name: "Soumettre au circuit" }).click();
  const submitResponse = await submitResponsePromise;
  expect(submitResponse.status(), "la main levée doit démarrer son circuit").toBe(200);
  expect(await submitResponse.json()).toMatchObject({
    id: created.id,
    status: "IN_APPROVAL",
  });

  const persisted = await browserApiGet<{ id: string; status: string; has_client_demande: boolean; has_generated_acte: boolean }>(
    page,
    `/guarantee-releases/${created.id}/`,
  );
  expect(persisted).toMatchObject({
    id: created.id,
    status: "IN_APPROVAL",
    has_client_demande: true,
    has_generated_acte: true,
  });
  expect(apiErrors, "réponses API en erreur").toEqual([]);
  expect(pageErrors, "erreurs JavaScript du navigateur").toEqual([]);
});

test("dation : configuration simulée, création d'un bien et soumission au circuit", async ({ page }) => {
  await loginDemoAdmin(page);
  const apiErrors: string[] = [];
  const pageErrors: string[] = [];
  page.on("response", (response) => {
    if (new URL(response.url()).pathname.startsWith(`${apiBasePath}/`) && response.status() >= 400) {
      apiErrors.push(`${response.request().method()} ${apiPath(response)} → ${response.status()}`);
    }
  });
  page.on("pageerror", (error) => pageErrors.push(error.message));

  const connectors = await browserApiGet<{
    results: Array<{ id: string; name: string; is_active: boolean }>;
  }>(page, "/cbs-connectors/?page_size=100");
  const connector = connectors.results.find(
    (item) => item.name === "CBS Filiale 01" && item.is_active,
  );
  expect(connector, "le connecteur Perfect simulé doit être actif en recette").toBeTruthy();

  await openPage(page, "/admin/connecteurs");
  await expect(page.getByRole("heading", { name: "Connecteurs Core Banking" })).toBeVisible();
  const connectorRow = page.getByRole("row").filter({ hasText: connector!.name });
  await connectorRow.getByRole("button", { name: "Modifier" }).click();
  await page.getByLabel("Encours client défaut").fill("1500000");
  const connectorPatchPromise = page.waitForResponse((response) =>
    isApiResponse(response, `/cbs-connectors/${connector!.id}/`, "PATCH"),
  );
  await page.locator("form").getByRole("button", { name: "Enregistrer", exact: true }).click();
  const connectorPatch = await connectorPatchPromise;
  expect(connectorPatch.status(), "le scénario de recette doit régler l'encours simulé").toBe(200);
  expect(await connectorPatch.json()).toMatchObject({
    id: connector!.id,
    mapping_rules: { simulate: { client_outstanding_default: "1500000" } },
  });

  const clients = await browserApiGet<{
    results: Array<{ id: string; cbs_client_id: string }>;
  }>(page, "/clients/?page_size=200");
  const client = clients.results.find((item) => Boolean(item.cbs_client_id));
  expect(client, "un client lié au simulateur CBS doit être disponible").toBeTruthy();

  const previewPromise = page.waitForResponse((response) =>
    isApiResponse(response, "/dation-requests/preview-cbs/")
      && new URL(response.url()).searchParams.get("cbs_client_id") === client!.cbs_client_id,
  );
  await openPage(page, `/dations/nouvelle?client=${client!.id}`);
  await expect(page.getByRole("heading", { name: "Nouvelle dation en paiement" })).toBeVisible();
  expect((await previewPromise).status(), "l'encours CBS simulé doit être consultable").toBe(200);
  const assetsSection = page.locator(".form-section").filter({ hasText: "3. Biens additionnels" });
  await assetsSection.getByRole("button", { name: "Ajouter", exact: true }).click();
  const assetDescription = `Bien recette ${Date.now()}`;
  await assetsSection.getByLabel("Description du bien").fill(assetDescription);
  await assetsSection.getByLabel("Valeur retenue").fill("1750000");

  const createResponsePromise = page.waitForResponse((response) =>
    isApiResponse(response, "/dation-requests/", "POST"),
  );
  await page.getByRole("button", { name: "Créer le brouillon" }).click();
  const createResponse = await createResponsePromise;
  expect(createResponse.status(), "le brouillon de dation doit être créé").toBe(201);
  const created = await createResponse.json() as {
    id: string;
    status: string;
    assets: Array<{ description: string; value: string }>;
  };
  expect(created.status).toBe("DRAFT");
  expect(created.assets).toContainEqual(expect.objectContaining({
    description: assetDescription,
    value: "1750000.00",
  }));

  const submitResponsePromise = page.waitForResponse((response) =>
    isApiResponse(response, `/dation-requests/${created.id}/submit/`, "POST"),
  );
  await page.getByRole("button", { name: "Soumettre au circuit" }).click();
  const submitResponse = await submitResponsePromise;
  expect(submitResponse.status(), "la dation doit démarrer son circuit").toBe(200);
  expect(await submitResponse.json()).toMatchObject({ id: created.id, status: "IN_APPROVAL" });

  const persisted = await browserApiGet<{ id: string; status: string; assets: Array<{ description: string }> }>(
    page,
    `/dation-requests/${created.id}/`,
  );
  expect(persisted.status).toBe("IN_APPROVAL");
  expect(persisted.assets).toContainEqual(expect.objectContaining({ description: assetDescription }));
  expect(apiErrors, "réponses API en erreur").toEqual([]);
  expect(pageErrors, "erreurs JavaScript du navigateur").toEqual([]);
});

test("contentieux : création depuis le recouvrement et persistance d'un événement juridique", async ({ page }) => {
  await loginDemoAdmin(page);
  const apiErrors: string[] = [];
  const pageErrors: string[] = [];
  page.on("response", (response) => {
    if (new URL(response.url()).pathname.startsWith(`${apiBasePath}/`) && response.status() >= 400) {
      apiErrors.push(`${response.request().method()} ${apiPath(response)} → ${response.status()}`);
    }
  });
  page.on("pageerror", (error) => pageErrors.push(error.message));

  const collectionCases = await browserApiGet<{
    results: Array<{ id: string; can_operate: boolean }>;
  }>(page, "/collection-cases/?open=1&page_size=200");
  const collectionCase = collectionCases.results.find((item) => item.can_operate);
  expect(collectionCase, "un dossier de recouvrement ouvert et opérable doit être disponible").toBeTruthy();

  const caseResponsePromise = page.waitForResponse((response) =>
    isApiResponse(response, `/collection-cases/${collectionCase!.id}/`),
  );
  await openPage(page, `/recouvrement/${collectionCase!.id}`);
  expect((await caseResponsePromise).status(), "la fiche recouvrement doit se charger").toBe(200);
  await expect(page.getByRole("button", { name: "Nouvelle procédure" })).toBeVisible();

  const createResponsePromise = page.waitForResponse((response) =>
    isApiResponse(response, "/litigations/", "POST"),
  );
  await page.getByRole("button", { name: "Nouvelle procédure" }).click();
  const createResponse = await createResponsePromise;
  expect(createResponse.status(), "la procédure doit être créée depuis le recouvrement").toBe(201);
  const litigation = await createResponse.json() as { id: string; case: string; status: string; events: unknown[] };
  expect(litigation).toMatchObject({ case: collectionCase!.id, status: "PRE_LITIGATION", events: [] });

  await expect(page.getByRole("heading", { name: "Procédure contentieuse" })).toBeVisible();
  const eventForm = page.locator("form").filter({
    has: page.getByRole("button", { name: "Ajouter", exact: true }),
  }).first();
  const eventDate = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
  const eventComment = `Audience de recette ${Date.now()}`;
  await eventForm.getByLabel("Date").fill(eventDate);
  await eventForm.getByLabel("Heure").fill("10:30");
  await eventForm.getByLabel("Lieu").fill("Tribunal de recette");
  await eventForm.getByLabel("Commentaire").fill(eventComment);
  const eventResponsePromise = page.waitForResponse((response) =>
    isApiResponse(response, `/litigations/${litigation.id}/events/`, "POST"),
  );
  await eventForm.getByRole("button", { name: "Ajouter", exact: true }).click();
  const eventResponse = await eventResponsePromise;
  expect(eventResponse.status(), "l'événement doit être enregistré").toBe(201);
  const event = await eventResponse.json() as {
    id: string;
    event_type: string;
    event_date: string;
    event_time: string;
    location: string;
    comment: string;
  };
  expect(event).toMatchObject({
    event_type: "HEARING",
    event_date: eventDate,
    event_time: "10:30:00",
    location: "Tribunal de recette",
    comment: eventComment,
  });

  const persistedPromise = page.waitForResponse((response) =>
    isApiResponse(response, `/litigations/${litigation.id}/`),
  );
  await page.reload({ waitUntil: "domcontentloaded" });
  const persistedResponse = await persistedPromise;
  expect(persistedResponse.status(), "la procédure et son agenda doivent être relisibles").toBe(200);
  const persisted = await persistedResponse.json() as {
    events: Array<{ id: string; comment: string; location: string }>;
  };
  expect(persisted.events).toContainEqual(expect.objectContaining({
    id: event.id,
    comment: eventComment,
    location: "Tribunal de recette",
  }));
  expect(apiErrors, "réponses API en erreur").toEqual([]);
  expect(pageErrors, "erreurs JavaScript du navigateur").toEqual([]);
});

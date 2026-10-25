import { expect, test, type Page } from "@playwright/test";

const tenantId = "tenant-e2e";

const modulePermissions = [
  "clients.view_client",
  "clients.add_client",
  "credits.view_creditapplication",
  "credits.add_creditapplication",
  "workflow.view_approvaltask",
  "guarantees.view_guarantee",
  "sureties.view_surety",
  "collections.view_collectioncase",
  "documents.view_document",
  "configuration.view_configurationprofile",
  "configuration.add_configurationprofile",
  "accounts.view_tenantrole",
];

function makeUser(permissions: string[]) {
  return {
    id: "user-e2e",
    username: "e2e-agent",
    email: "e2e@example.test",
    first_name: "Awa",
    last_name: "Test",
    tenant: tenantId,
    agency: "agency-e2e",
    agencies_detail: [],
    data_scope: "TENANT" as const,
    is_group_level: false,
    is_staff: false,
    is_superuser: false,
    mfa_enabled: false,
    must_change_password: false,
    roles: ["Recette"],
    capabilities: ["tenant_admin"],
    permissions,
    tenant_branding: null,
  };
}

const clientFixture = {
  id: "client-e2e",
  reference: "E2E-CLI-001",
  cbs_client_id: "",
  client_type: "INDIVIDUAL",
  display_name: "Awa Koné E2E",
  first_name: "Awa",
  last_name: "Koné",
};

const editableCreditFixture = {
  id: "app-e2e",
  reference: "DOS-E2E-001",
  client: clientFixture.id,
  client_display: clientFixture.display_name,
  client_type: "INDIVIDUAL",
  product: "product-e2e",
  product_label: "Trésorerie recette",
  agency: "agency-e2e",
  amount_requested: "1000000",
  amount_proposed: "1000000",
  amount_approved: null,
  currency: "XOF",
  interest_rate: "12.5",
  fees_rate: "0",
  mandatory_savings_rate: "0",
  periodicity: "MONTHLY",
  duration_months: 12,
  repayment_mechanism: "DEGRESSIVE",
  status: "DRAFT",
  status_display: "Brouillon",
  document_checklist: [],
  documents: [],
  extra_fees: [],
};

const paginated = (results: unknown[] = []) => ({
  count: results.length,
  next: null,
  previous: null,
  results,
});

function simulationFixture() {
  return {
    parameters: {
      amount: "1000000",
      annual_rate: "12.5",
      savings_rate: "0",
      months: 12,
      periodicity: "MONTHLY",
      mechanism: "DEGRESSIVE",
      simulation_date: "2026-10-25",
      first_due_date: null,
      currency: "XOF",
    },
    installment: "88848",
    monthly_payment: "88848",
    client_total_first: "88848",
    total_repayment: "1066176",
    total_institution: "1066176",
    total_interest: "666176",
    total_savings: "0",
    schedule: [
      {
        number: 1,
        due_date: "2026-11-25",
        principal: "78431",
        interest: "10417",
        savings: "0",
        institution_due: "88848",
        total: "88848",
        balance: "921569",
      },
    ],
  };
}

async function installApiMocks(
  page: Page,
  options: {
    user?: ReturnType<typeof makeUser>;
    failures?: Record<string, number>;
    financingObjectRequired?: boolean;
    mutationErrors?: Record<string, unknown>;
  } = {},
) {
  const user = options.user ?? makeUser(modulePermissions);
  const failures = { ...(options.failures ?? {}) };
  const requests: { path: string; method: string; url: string }[] = [];

  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace(/^\/api\/v1/, "") || "/";
    const canonicalPath = path.endsWith("/") ? path : `${path}/`;
    const method = request.method();
    requests.push({ path, method, url: request.url() });

    if (path === "/auth/token/" && method === "POST") {
      await route.fulfill({ json: { access: "e2e-access", refresh: "e2e-refresh" } });
      return;
    }
    if (path === "/auth/token/refresh/" && method === "POST") {
      await route.fulfill({ json: { access: "e2e-access-refreshed" } });
      return;
    }
    if (path === "/users/me/") {
      await route.fulfill({ json: user });
      return;
    }
    if (path === "/tenants/branding/") {
      await route.fulfill({
        json: {
          id: tenantId,
          code: "FIL01",
          name: "Filiale recette",
          logo_url: null,
          brand_primary: "#173f5f",
          brand_secondary: "#20639b",
          brand_accent: "#f6d55c",
          brand_sidebar: "#173f5f",
          brand_sidebar_text: "#ffffff",
        },
      });
      return;
    }
    if (path === `/tenants/${tenantId}/`) {
      await route.fulfill({
        json: {
          id: tenantId,
          code: "FIL01",
          name: "Filiale recette",
          logo_url: null,
          brand_primary: "#173f5f",
          brand_secondary: "#20639b",
          brand_accent: "#f6d55c",
          brand_sidebar: "#173f5f",
          brand_sidebar_text: "#ffffff",
        },
      });
      return;
    }
    if (path === "/tenants/") {
      await route.fulfill({ json: paginated([]) });
      return;
    }
    const failureKey = failures[path] !== undefined ? path : canonicalPath;
    if (method === "GET" && (failures[failureKey] ?? 0) > 0) {
      failures[failureKey] -= 1;
      await route.fulfill({
        status: 503,
        json: { detail: "Erreur temporaire de recette." },
      });
      return;
    }
    if (path === "/clients/" && url.searchParams.get("search") === "E2E") {
      await route.fulfill({ json: paginated([clientFixture]) });
      return;
    }
    if (path === "/clients/client-e2e/") {
      await route.fulfill({ json: clientFixture });
      return;
    }
    if (path === "/credit-applications/app-e2e/") {
      await route.fulfill({
        json: {
          id: "app-e2e",
          reference: "DOS-E2E-001",
          client: clientFixture.id,
          client_display: clientFixture.display_name,
          amount_requested: "1000000",
          amount_proposed: "1000000",
          amount_approved: null,
          currency: "XOF",
        },
      });
      return;
    }
    if (path === "/credit-products/") {
      await route.fulfill({
        json: paginated([
          {
            id: "product-e2e",
            code: "TRESO-E2E",
            label: "Trésorerie recette",
            currency: "XOF",
            client_type: "ALL",
            interest_rate: "12.5",
          },
        ]),
      });
      return;
    }
    if (path === "/credit-applications/configuration-context/") {
      await route.fulfill({
        json: {
          financing_object_required: options.financingObjectRequired ?? false,
          sources: [],
          pricing: {
            tariff: {
              engine: "LEGACY",
              currency: "XOF",
              charges: [],
              allow_manual_fees: true,
            },
          },
        },
      });
      return;
    }
    if (path === "/configuration-profiles/catalogue/") {
      await route.fulfill({
        json: {
          policy: [],
          thresholds: [],
          analysis_fields: [],
          detail_tables: [],
          precedence: [],
          eligibility_criteria: [],
          score_metrics: [],
        },
      });
      return;
    }
    if (path === "/collection-cases/agent-dashboard/") {
      await route.fulfill({
        json: {
          assigned_open: 0,
          unassigned_open: 0,
          followups_due: 0,
          pending_promises: 0,
          broken_promises_30d: 0,
          repayments_this_month_count: 0,
          repayments_this_month_amount: "0",
          by_par_class: {},
          by_stage: {},
          due_followups: [],
          as_of: "2026-10-25",
        },
      });
      return;
    }
    if (path === "/collection-cases/hearings-agenda/") {
      await route.fulfill({ json: [] });
      return;
    }
    if (path === "/collection-cases/case-e2e/" && method === "GET") {
      await route.fulfill({
        json: {
          id: "case-e2e",
          loan: "loan-e2e",
          loan_status: "ACTIVE",
          loan_principal: "1000000",
          application_id: "app-e2e",
          application_reference: "DOS-E2E-001",
          client_id: clientFixture.id,
          client_name: clientFixture.display_name,
          agency_name: "Agence recette",
          stage: "AMICABLE",
          stage_display: "Amiable",
          par_class: "PAR30",
          par_class_display: "PAR 30",
          days_overdue: 35,
          overdue_amount: "50000",
          assigned_to: null,
          assigned_to_name: null,
          can_operate: true,
          can_collect: false,
          financial_ops_frozen: false,
          created_at: "2026-10-01T10:00:00Z",
          actions: [],
          promises: [],
          dialogue: [],
          stage_history: [],
          restructures: [],
          write_offs: [],
          litigations: [],
          repayments: [],
          installments: [],
          guarantees: [],
          dation_requests: [],
          surety_engagements: [],
          core_banking_reference: "CBS-E2E-001",
        },
      });
      return;
    }
    if (path === "/credit-applications/simulate/" && method === "POST") {
      await route.fulfill({ json: simulationFixture() });
      return;
    }
    if (path === "/guarantees/" && method === "POST" && options.mutationErrors) {
      await route.fulfill({ status: 400, json: { errors: options.mutationErrors } });
      return;
    }

    await route.fulfill({ json: method === "GET" ? paginated([]) : {} });
  });

  return {
    requests,
    clearFailure(path: string) {
      failures[path] = 0;
    },
  };
}

async function authenticateInBrowser(page: Page, user = makeUser(modulePermissions)) {
  await installApiMocks(page, { user });
  await page.addInitScript((id) => {
    localStorage.setItem("finflow_access", "e2e-access");
    localStorage.setItem("finflow_refresh", "e2e-refresh");
    localStorage.setItem("finflow_tenant", id);
  }, tenantId);
}

async function openPage(page: Page, path: string) {
  // Vite's development server can keep loading many module chunks after the
  // document is interactive; assertions below wait for each screen to render.
  await page.goto(path, { waitUntil: "domcontentloaded" });
}

test("la connexion ouvre la page autorisée et les filtres clients déclenchent la recherche", async ({ page }) => {
  const user = makeUser(["clients.view_client"]);
  const { requests } = await installApiMocks(page, { user });

  await openPage(page, "/login");
  await page.getByPlaceholder("ex. FIL01").fill("FIL01");
  await page.getByPlaceholder("votre identifiant").fill("e2e-agent");
  await page.getByPlaceholder("••••••••").fill("mot-de-passe-factice");
  await page.getByRole("button", { name: "Se connecter" }).click();

  await expect(page).toHaveURL(/\/clients$/);
  await expect(page.getByRole("heading", { name: "Clients" })).toBeVisible();
  await expect(page.getByText("Aucun client ne correspond à ces critères.")).toBeVisible();
  await expect(page.getByRole("link", { name: "Dossiers de crédit" })).toHaveCount(0);

  const clientSearch = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return url.pathname.endsWith("/clients/") && url.searchParams.get("search") === "recherche-e2e";
  });
  await page.getByPlaceholder("Nom, référence, téléphone, pièce, CBS…").fill("recherche-e2e");
  await clientSearch;
  expect(requests.some((request) => request.path === "/auth/token/" && request.method === "POST")).toBe(true);

  await openPage(page, "/admin/roles");
  await expect(page.getByText("Vous n'avez pas les droits pour accéder à cette page.")).toBeVisible();
});

test("le profil enregistre les coordonnées, valide le mot de passe et délègue ses tâches", async ({ page }) => {
  const user = makeUser([]);
  const { requests } = await installApiMocks(page, { user });
  await page.addInitScript((id) => {
    localStorage.setItem("finflow_access", "e2e-access");
    localStorage.setItem("finflow_refresh", "e2e-refresh");
    localStorage.setItem("finflow_tenant", id);
  }, tenantId);

  const colleague = { id: "delegate-profile-e2e", username: "agent-e2e", display_name: "Agent recette" };
  let profilePayload: Record<string, unknown> | null = null;
  let delegationPayload: Record<string, unknown> | null = null;
  let passwordPayload: Record<string, unknown> | null = null;
  await page.route(/\/api\/v1\/delegations\//, async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path.endsWith("/colleagues/") && request.method() === "GET") {
      await route.fulfill({ json: [colleague] });
    } else if (path.endsWith("/mine/") && request.method() === "GET") {
      await route.fulfill({ json: [] });
    } else if (path.endsWith("/give/") && request.method() === "POST") {
      delegationPayload = request.postDataJSON() as Record<string, unknown>;
      await route.fulfill({
        json: {
          id: "profile-delegation-e2e", delegator: user.id,
          delegator_display: user.username, delegate: colleague.id,
          delegate_display: colleague.display_name, ...delegationPayload,
          is_active: true, is_currently_valid: true, created_at: "2026-10-25T10:00:00Z",
        },
      });
    } else {
      await route.fallback();
    }
  });
  await page.route(/\/api\/v1\/users\/me\/$/, async (route) => {
    if (route.request().method() === "PATCH") {
      profilePayload = route.request().postDataJSON() as Record<string, unknown>;
      await route.fulfill({ json: { ...user, ...profilePayload } });
      return;
    }
    await route.fallback();
  });
  await page.route(/\/api\/v1\/users\/me\/change-password\/$/, async (route) => {
    if (route.request().method() === "POST") {
      passwordPayload = route.request().postDataJSON() as Record<string, unknown>;
      await route.fulfill({ json: { detail: "Mot de passe modifié.", must_change_password: false } });
      return;
    }
    await route.fallback();
  });

  await openPage(page, "/profil");
  await expect(page.getByRole("heading", { name: "Mon profil" })).toBeVisible();
  await page.getByLabel("Prénom").fill("Awa Mise à jour");
  await page.getByLabel("Nom", { exact: true }).fill("Koné Recette");
  await page.getByLabel("E-mail *").fill("awa.recette@example.test");
  const profileResponse = page.waitForResponse((response) =>
    new URL(response.url()).pathname.endsWith("/users/me/")
      && response.request().method() === "PATCH",
  );
  await page.getByRole("button", { name: "Enregistrer le profil" }).click();
  await profileResponse;
  expect(profilePayload).toEqual({
    first_name: "Awa Mise à jour", last_name: "Koné Recette",
    email: "awa.recette@example.test",
  });
  await expect(page.getByText("Profil mis à jour.", { exact: true })).toBeVisible();

  await page.getByLabel("Mot de passe actuel *").fill("ancien-mot-de-passe");
  await page.getByLabel("Nouveau mot de passe * (≥ 10 car.)").fill("nouveau-mot-de-passe");
  await page.getByLabel("Confirmation *").fill("confirmation-differente");
  await page.getByRole("button", { name: "Mettre à jour le mot de passe" }).click();
  await expect(page.getByText("Les mots de passe ne correspondent pas.", { exact: true })).toBeVisible();
  expect(requests.some((request) => request.path === "/users/me/change-password/" && request.method === "POST")).toBe(false);

  await page.getByLabel("Confirmation *").fill("nouveau-mot-de-passe");
  const passwordResponse = page.waitForResponse((response) =>
    response.url().endsWith("/api/v1/users/me/change-password/")
      && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Mettre à jour le mot de passe" }).click();
  await passwordResponse;
  expect(passwordPayload).toEqual({
    current_password: "ancien-mot-de-passe",
    new_password: "nouveau-mot-de-passe",
    new_password_confirm: "nouveau-mot-de-passe",
  });
  await expect(page.getByText("Mot de passe mis à jour.", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Mot de passe actuel *")).toHaveValue("");

  await page.getByLabel("Délégataire *").selectOption(colleague.id);
  await page.getByLabel("Motif").fill("Mission temporaire");
  await page.getByLabel("Début *").fill("2026-11-01");
  await page.getByLabel("Fin *").fill("2026-11-07");
  const delegationResponse = page.waitForResponse((response) =>
    response.url().endsWith("/api/v1/delegations/give/")
      && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Déléguer mes pouvoirs" }).click();
  await delegationResponse;
  expect(delegationPayload).toEqual({
    delegate: colleague.id, start_date: "2026-11-01", end_date: "2026-11-07",
    reason: "Mission temporaire",
  });
  await expect(page.getByText("Délégation créée. Le délégataire verra vos tâches en attente.", { exact: true })).toBeVisible();
});

test("la première connexion impose le nouveau mot de passe puis ouvre la page autorisée", async ({ page }) => {
  const user = {
    ...makeUser(["reporting.view_dashboard"]),
    must_change_password: true,
  };
  await installApiMocks(page, { user });
  await page.addInitScript((id) => {
    localStorage.setItem("finflow_access", "e2e-access");
    localStorage.setItem("finflow_refresh", "e2e-refresh");
    localStorage.setItem("finflow_tenant", id);
  }, tenantId);

  let passwordPayload: Record<string, unknown> | null = null;
  let passwordChanged = false;
  await page.route(/\/api\/v1\/users\/me\/change-password\/$/, async (route) => {
    if (route.request().method() === "POST") {
      passwordPayload = route.request().postDataJSON() as Record<string, unknown>;
      passwordChanged = true;
      await route.fulfill({ json: { detail: "Mot de passe modifié.", must_change_password: false } });
      return;
    }
    await route.fallback();
  });
  await page.route(/\/api\/v1\/users\/me\/$/, async (route) => {
    if (route.request().method() === "GET" && passwordChanged) {
      await route.fulfill({ json: { ...user, must_change_password: false } });
      return;
    }
    await route.fallback();
  });

  await openPage(page, "/changer-mot-de-passe");
  await expect(page.getByRole("heading", { name: "FIN_FLOW" })).toBeVisible();
  await page.getByLabel("Mot de passe temporaire (reçu par e-mail) *").fill("temporaire-e2e");
  await page.getByLabel("Nouveau mot de passe * (≥ 10 car.)").fill("nouveau-secret-e2e");
  await page.getByLabel("Confirmer le nouveau mot de passe *").fill("mauvaise-confirmation");
  await page.getByRole("button", { name: "Enregistrer et continuer" }).click();
  await expect(page.getByText("Les mots de passe ne correspondent pas.", { exact: true })).toBeVisible();
  expect(passwordPayload).toBeNull();

  await page.getByLabel("Confirmer le nouveau mot de passe *").fill("nouveau-secret-e2e");
  const passwordResponse = page.waitForResponse((response) =>
    response.url().endsWith("/api/v1/users/me/change-password/")
      && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Enregistrer et continuer" }).click();
  await passwordResponse;
  await expect(page).toHaveURL(/\/$/);
  expect(passwordPayload).toEqual({
    current_password: "temporaire-e2e",
    new_password: "nouveau-secret-e2e",
    new_password_confirm: "nouveau-secret-e2e",
  });
});

test("le tableau de bord affiche ses indicateurs et applique le filtre de période", async ({ page }) => {
  const user = makeUser([
    "reporting.view_dashboard", "credits.view_creditapplication",
    "collections.view_collectioncase",
  ]);
  await installApiMocks(page, { user });
  await page.addInitScript((id) => {
    localStorage.setItem("finflow_access", "e2e-access");
    localStorage.setItem("finflow_refresh", "e2e-refresh");
    localStorage.setItem("finflow_tenant", id);
  }, tenantId);

  await page.route(/\/api\/v1\/reporting\/dashboard\//, async (route) => {
    await route.fulfill({
      json: {
        scope: "FILIALE",
        credits: {
          summary: {
            total: 5, amount_requested: "5000000", amount_approved: "2000000",
            approved_count: 1, rejected_count: 0, returned_count: 0,
            draft_count: 2, disbursed_count: 1, disbursed_amount: "2000000",
            pending_count: 1, in_approval_count: 1, contract_generated_count: 0,
            disbursement_pending_count: 0, disbursement_pending_amount: "0",
          },
          by_status: [], by_product: [], by_agency: [], monthly: [], recent: [],
          funnel: {
            submitted: 1, in_approval: 1, approved: 1, disbursed: 1,
            rejected: 0, returned: 0, approval_rate_pct: 100,
            disbursement_rate_pct: 100,
          },
        },
        portfolio: {
          active_loans: 1, total_loans: 1, disbursed_total: "2000000",
          outstanding: "1250000", overdue_installments: 2,
        },
        clients: { total: 1, by_type: [], new_this_month: 1 },
        guarantees: { count: 2, active_count: 2, total_current_value: "3000000", active_value: "3000000" },
        risk: {
          by_par_class: [], by_stage: [], open_cases: 2, total_overdue: "150000",
          followups_due: 1, pending_promises: 3, broken_promises_30d: 0,
        },
        workflow: {
          pending_tasks: 4, overdue_tasks: 1, my_pending_tasks: 2,
          my_overdue_tasks: 0, conditions_pending: 0,
        },
      },
    });
  });

  await openPage(page, "/");
  await expect(page.getByRole("heading", { name: /Awa/ })).toBeVisible();
  await expect(page.getByText("Encours", { exact: true })).toBeVisible();
  await expect(page.getByText("1 prêt(s) actif(s)", { exact: true })).toBeVisible();

  const filteredRequest = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return url.pathname.endsWith("/reporting/dashboard/")
      && url.searchParams.get("date_from") === "2026-10-01";
  });
  await page.locator(".dashboard-page input[type='date']").first().fill("2026-10-01");
  await filteredRequest;
});

test("le détail d'un dossier charge ses synthèses et expose l'analyse au contributeur", async ({ page }) => {
  const user = makeUser([
    "credits.view_creditapplication", "credits.add_financialanalysis",
  ]);
  await installApiMocks(page, { user });
  await page.addInitScript((id) => {
    localStorage.setItem("finflow_access", "e2e-access");
    localStorage.setItem("finflow_refresh", "e2e-refresh");
    localStorage.setItem("finflow_tenant", id);
  }, tenantId);

  const application = {
    id: "app-e2e", reference: "DOS-E2E-001", client: clientFixture.id,
    client_display: clientFixture.display_name, client_reference: clientFixture.reference,
    client_type: "INDIVIDUAL", product: "product-e2e", product_label: "Crédit test",
    agency: "agency-e2e", amount_requested: "1000000", amount_proposed: "1000000",
    amount_approved: null, interest_rate: "12", fees_rate: "0",
    mandatory_savings_rate: "0", periodicity: "MONTHLY", duration_months: 12,
    first_due_date: null, last_due_date: null, repayment_mechanism: "DEGRESSIVE",
    purpose_type: "PERSONAL", purpose: "Trésorerie", currency: "XOF",
    dependents_count: 2, status: "DRAFT", status_display: "Brouillon",
    created_by: user.id, submitted_by: user.id,
  };
  await page.route(/\/api\/v1\/credit-applications\/app-e2e\//, async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/v1/credit-applications/app-e2e/readiness/") {
      await route.fulfill({
        json: {
          policy: {
            allow_collateral_during_approval: false, enable_cancel_status: false,
            require_setup_request: false, require_setup_four_eyes: false,
          },
          show_checklist: false, ready: true, checks: [],
        },
      });
    } else if (path === "/api/v1/credit-applications/app-e2e/collateral-summary/") {
      await route.fulfill({
        json: {
          reference_amount: "1000000", currency: "XOF", guarantees: [],
          guarantees_gross_total: "0", guarantees_retained_total: "0",
          guarantee_coverage_pct: null, guarantee_gap: null,
          min_guarantee_coverage: "100", guarantee_ok: null, sureties: [],
          sureties_total: "0", surety_coverage_pct: null,
          requires_guarantee: false, alerts: [], haircuts: {},
        },
      });
    } else if (path === "/api/v1/credit-applications/app-e2e/") {
      await route.fulfill({ json: application });
    } else {
      await route.fallback();
    }
  });

  await openPage(page, "/dossiers/app-e2e");
  await expect(page.locator(".credit-hero-ref")).toContainText("DOS-E2E-001");
  await expect(page.locator(".credit-hero-actions").getByRole("link", { name: "Ajouter une analyse" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Garanties réelles", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Cautions (pilier séparé)", exact: true })).toBeVisible();
});

test("le détail client affiche son portefeuille sans exposer la modification à un lecteur", async ({ page }) => {
  const user = makeUser([
    "clients.view_client", "credits.view_creditapplication",
    "guarantees.view_guarantee", "sureties.view_surety",
    "collections.view_collectioncase", "documents.view_document",
    "guarantees.view_dationrequest", "guarantees.view_guaranteeformalizationrequest",
    "guarantees.view_guaranteereleaserequest",
  ]);
  const { requests } = await installApiMocks(page, { user });
  await page.addInitScript((id) => {
    localStorage.setItem("finflow_access", "e2e-access");
    localStorage.setItem("finflow_refresh", "e2e-refresh");
    localStorage.setItem("finflow_tenant", id);
  }, tenantId);

  await openPage(page, "/clients/client-e2e");
  await expect(page.getByRole("heading", { name: "Awa Koné", exact: true })).toBeVisible();
  await expect(page.getByText("Portefeuille", { exact: true })).toBeVisible();
  await expect(page.locator(".client-detail-page").getByText("Dossiers de crédit", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Modifier", exact: true })).toHaveCount(0);
  expect(requests.some((request) => request.path === "/credit-applications/"
    && new URL(request.url).searchParams.get("client") === clientFixture.id)).toBe(true);
  expect(requests.some((request) => request.path === "/guarantees/"
    && new URL(request.url).searchParams.get("client") === clientFixture.id)).toBe(true);
});

test("la file de validations filtre les dossiers et masque un lien hors périmètre", async ({ page }) => {
  const user = makeUser(["workflow.view_approvaltask"]);
  await installApiMocks(page, { user });
  await page.addInitScript((id) => {
    localStorage.setItem("finflow_access", "e2e-access");
    localStorage.setItem("finflow_refresh", "e2e-refresh");
    localStorage.setItem("finflow_tenant", id);
  }, tenantId);

  const formalizationTask = {
    id: "formalization-task-e2e", target_kind: "FORMALISATION",
    detail_path: "/formalisations/formalization-e2e", reference: "FOR-E2E-001",
    client_display: "Client recette", client_type: "INDIVIDUAL",
    client_type_display: "Particulier", amount_requested: "500000",
    amount_proposed: null, currency: "XOF", status: "IN_APPROVAL",
    status_display: "En validation", product_label: "Formalisation",
    created_by_display: "Gestionnaire recette", created_at: "2026-10-20T10:00:00Z",
    definition_name: "Circuit juridique", instance_status: "IN_PROGRESS",
    current_step_name: "Validation juridique", current_step_role: "LEGAL",
    current_step_label: "Juridique", current_order: 1, my_task_status: "PENDING",
    my_step_name: "Juridique", my_step_order: 1, my_task_due_at: null,
    is_actionable: true, is_treated: false,
  };
  await page.route(/\/api\/v1\/approval-tasks\/my_dossiers\//, async (route) => {
    const url = new URL(route.request().url());
    const showTask = url.searchParams.get("queue") === "all";
    await route.fulfill({
      json: {
        count: showTask ? 1 : 0, next: null, previous: null,
        results: showTask ? [formalizationTask] : [],
        actionable_count: 1, treated_count: 0, visible_count: 1,
        step_options: [{ value: "LEGAL", label: "Validation juridique" }],
      },
    });
  });

  await openPage(page, "/taches");
  await expect(page.getByRole("heading", { name: "Mes validations" })).toBeVisible();
  await expect(page.getByText("Aucun dossier en circuit pour votre périmètre.", { exact: true })).toBeVisible();
  const response = page.waitForResponse((item) => {
    const url = new URL(item.url());
    return url.pathname.endsWith("/approval-tasks/my_dossiers/")
      && url.searchParams.get("queue") === "all";
  });
  await page.locator(".page-shell--list select").first().selectOption("all");
  await response;
  await expect(page.getByText("FOR-E2E-001", { exact: true })).toBeVisible();
  await expect(page.getByText("Ouvrir le dossier", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "FOR-E2E-001" })).toHaveCount(0);
});

test("la consolidation Groupe affiche les indicateurs et change l'axe de lecture", async ({ page }) => {
  const user = {
    ...makeUser(["reporting.view_dashboard"]),
    is_group_level: true,
    is_staff: true,
    data_scope: "GROUP" as const,
  };
  await installApiMocks(page, { user });
  await page.addInitScript((id) => {
    localStorage.setItem("finflow_access", "e2e-access");
    localStorage.setItem("finflow_refresh", "e2e-refresh");
    localStorage.setItem("finflow_tenant", id);
  }, tenantId);

  await page.route(/\/api\/v1\/reporting\/group-consolidation\//, async (route) => {
    await route.fulfill({
      json: {
        credits: { summary: {
          total: 3, amount_requested: "7500000", amount_approved: "4000000",
          disbursed_amount: "2000000",
        } },
        portfolio: { active_loans: 2, overdue_installments: 1 },
      },
    });
  });
  await page.route(/\/api\/v1\/reporting\/group-breakdown\//, async (route) => {
    const dimension = new URL(route.request().url()).searchParams.get("dimension");
    const row = dimension === "country"
      ? { "tenant__country": "Sénégal", count: 3, amount_requested: "7500000", amount_approved: "4000000" }
      : { tenant_id: "FIL01", count: 3, amount_requested: "7500000", amount_approved: "4000000" };
    await route.fulfill({ json: { dimension, rows: [row] } });
  });

  await openPage(page, "/admin/consolidation");
  await expect(page.getByRole("heading", { name: "Consolidation Groupe" })).toBeVisible();
  await expect(page.getByText("FIL01", { exact: true })).toBeVisible();
  const countryBreakdown = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return url.pathname.endsWith("/reporting/group-breakdown/")
      && url.searchParams.get("dimension") === "country";
  });
  await page.locator(".page-shell select").first().selectOption("country");
  await countryBreakdown;
  await expect(page.getByText("Sénégal", { exact: true })).toBeVisible();
});

test("les détails garantie et caution restent lisibles sans permission de modification", async ({ page }) => {
  const user = makeUser(["guarantees.view_guarantee", "sureties.view_surety"]);
  await installApiMocks(page, { user });
  await page.addInitScript((id) => {
    localStorage.setItem("finflow_access", "e2e-access");
    localStorage.setItem("finflow_refresh", "e2e-refresh");
    localStorage.setItem("finflow_tenant", id);
  }, tenantId);

  const guarantee = {
    id: "guarantee-detail-e2e", reference: "GAR-E2E-01",
    guarantee_type: "MORTGAGE", type_display: "Hypothèque", pledge_category: "",
    client: clientFixture.id, client_display: clientFixture.display_name,
    application: null, description: "Maison familiale", owners: "Awa Koné",
    expertise_value: "600000", current_value: "500000", is_insured: true,
    insurance_reference: "ASS-E2E", owner_last_name: "Koné", owner_first_name: "Awa",
    owner_marital_status: "", matrimonial_regime: "", document_type: "TITLE",
    document_number: "TF-E2E-01", document_issue_date: null,
    address: "Dakar", expertise_date: null, expertise_firm: "Cabinet recette",
    expert_name: "Expert test", value_to_consider: "500000", ltv_ratio: null,
    occupancy_status: "OWNER", document_scan: null, expertise_report_scan: null,
    lease_contract_scan: null, legal_situation_certificate_scan: null,
    status: "ACTIVE", status_display: "Active", photos: [], documents: [], movements: [],
    open_formalization_id: null, open_dation_id: null, open_release_id: null,
  };
  const surety = {
    id: "surety-detail-e2e", surety_type: "PHYSICAL", display_name: "Mariam Garante",
    name: "Mariam Garante", first_name: "Mariam", last_name: "Garante",
    birth_date: null, birth_country: "Sénégal", activity: "Commerçante",
    estimated_income: "350000", id_document_type: "NATIONAL_ID", national_id: "ID-E2E",
    id_document_issue_date: null, id_document_expiry_date: null, id_document_scan: null,
    photo: null, company_name: "", legal_form: "", ifu: "", rccm: "", ifu_scan: null,
    rccm_scan: null, city: "Dakar", manager_last_name: "", manager_first_name: "",
    manager_phone: "", manager_email: "", manager_address: "", manager_id_document_type: "",
    manager_id_document_number: "", manager_id_document_issue_date: null,
    manager_id_document_expiry_date: null, manager_id_document_scan: null,
    manager_position: "", manager_birth_date: null, manager_birth_country: "",
    manager_birth_city: "", identifier: "ID-E2E", phone: "770000001", email: "",
    address: "Dakar", phones: [], documents: [], commitment_ceiling: "500000",
    total_committed: "100000", available_ceiling: "400000", is_active: true,
    engagements: [], created_at: "2026-10-20T10:00:00Z",
  };
  await page.route(/\/api\/v1\/guarantees\/guarantee-detail-e2e\//, async (route) => {
    await route.fulfill({ json: guarantee });
  });
  await page.route(/\/api\/v1\/sureties\/surety-detail-e2e\//, async (route) => {
    await route.fulfill({ json: surety });
  });

  await openPage(page, "/garanties/guarantee-detail-e2e");
  await expect(page.getByRole("heading", { name: "Hypothèque", exact: true })).toBeVisible();
  await expect(page.locator(".client-banner-ref").getByText("GAR-E2E-01", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Modifier", exact: true })).toHaveCount(0);

  await openPage(page, "/cautions/surety-detail-e2e");
  await expect(page.getByRole("heading", { name: "Mariam Garante", exact: true })).toBeVisible();
  await expect(page.getByText("Aucun engagement enregistré.", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Modifier", exact: true })).toHaveCount(0);
});

test("le contentieux enregistre un événement juridique avec sa date et son lieu", async ({ page }) => {
  const user = makeUser([
    "collections.view_litigationfile", "collections.add_litigationevent",
  ]);
  await installApiMocks(page, { user });
  await page.addInitScript((id) => {
    localStorage.setItem("finflow_access", "e2e-access");
    localStorage.setItem("finflow_refresh", "e2e-refresh");
    localStorage.setItem("finflow_tenant", id);
  }, tenantId);

  const litigation = {
    id: "litigation-e2e", case: "case-e2e", title: "Procédure de recette",
    action_type: "SUMMONS", action_type_display: "Assignation",
    court_name: "Tribunal de recette", court_registry: "Greffe 01",
    case_reference: "RG-E2E-01", chamber: "Civile", lawyer: "", bailiff: "",
    filing_date: null, hearing_date: null, status: "IN_PROGRESS",
    status_display: "En cours", notes: "Dossier juridique de test",
    events: [], seizures: [], costs: [], can_operate: true,
    created_at: "2026-10-20T10:00:00Z", updated_at: "2026-10-20T10:00:00Z",
  };
  let eventPayload: Record<string, unknown> | null = null;
  await page.route(/\/api\/v1\/litigations\/litigation-e2e\//, async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/api/v1/litigations/litigation-e2e/" && request.method() === "GET") {
      await route.fulfill({ json: litigation });
    } else if (path.endsWith("/litigation-e2e/documents/")) {
      await route.fulfill({ json: [] });
    } else if (path.endsWith("/litigation-e2e/events/") && request.method() === "POST") {
      eventPayload = request.postDataJSON() as Record<string, unknown>;
      await route.fulfill({ json: { id: "event-e2e", ...eventPayload }, status: 201 });
    } else {
      await route.fallback();
    }
  });

  await openPage(page, "/recouvrement/case-e2e/contentieux/litigation-e2e");
  await expect(page.getByRole("heading", { name: "Procédure de recette" })).toBeVisible();
  const eventForm = page.locator("form").filter({
    has: page.getByRole("button", { name: "Ajouter", exact: true }),
  }).first();
  await eventForm.getByLabel("Date").fill("2026-11-05");
  await eventForm.getByLabel("Heure").fill("10:30");
  await eventForm.getByLabel("Lieu").fill("Tribunal de recette");
  await eventForm.getByLabel("Commentaire").fill("Audience de mise en état");
  const eventResponse = page.waitForResponse((response) =>
    response.url().endsWith("/api/v1/litigations/litigation-e2e/events/")
      && response.request().method() === "POST",
  );
  await eventForm.getByRole("button", { name: "Ajouter", exact: true }).click();
  await eventResponse;
  expect(eventPayload).toMatchObject({
    event_type: "HEARING", event_date: "2026-11-05", event_time: "10:30",
    location: "Tribunal de recette", comment: "Audience de mise en état",
  });
  await expect(page.getByText("Événement ajouté.", { exact: true })).toBeVisible();
});

test("le hub après-vente filtre ses modules selon les permissions", async ({ page }) => {
  const user = makeUser([
    "guarantees.view_guaranteereleaserequest",
    "guarantees.initiate_guaranteereleaserequest",
  ]);
  await installApiMocks(page, { user });
  await page.addInitScript((id) => {
    localStorage.setItem("finflow_access", "e2e-access");
    localStorage.setItem("finflow_refresh", "e2e-refresh");
    localStorage.setItem("finflow_tenant", id);
  }, tenantId);
  await page.route(/\/api\/v1\/reporting\/after-sales-hub\//, async (route) => {
    await route.fulfill({
      json: {
        modules: {
          main_levee: { open: 2, in_approval: 1 },
          dation: { open: 5, in_approval: 2 },
          formalisation: { open: 1, in_approval: 0 },
          collection: { open: 3, followups_due: 1, unassigned: 1 },
        },
        recent: [], as_of: "2026-10-25",
      },
    });
  });

  await openPage(page, "/apres-vente");
  await expect(page.getByRole("heading", { name: "Après-vente" })).toBeVisible();
  await expect(page.locator(".detail-grid").getByText("Mains levées", { exact: true })).toBeVisible();
  await expect(page.locator(".detail-grid").getByText("Dations", { exact: true })).toHaveCount(0);
  await expect(page.locator(".detail-grid").getByRole("link", { name: "Nouvelle" })).toHaveAttribute("href", "/mains-levees/nouvelle");
  await expect(page.getByText("Aucun dossier après-vente ouvert.", { exact: true })).toBeVisible();
});

test("les routes directes des modules restent protégées sans leur permission", async ({ page }) => {
  const user = makeUser(["clients.view_client"]);
  const { requests } = await installApiMocks(page, { user });
  await page.addInitScript((id) => {
    localStorage.setItem("finflow_access", "e2e-access");
    localStorage.setItem("finflow_refresh", "e2e-refresh");
    localStorage.setItem("finflow_tenant", id);
  }, tenantId);

  for (const path of ["/dossiers/nouveau", "/documents", "/recouvrement"]) {
    await openPage(page, path);
    await expect(page.getByText("Vous n'avez pas les droits pour accéder à cette page.", { exact: true })).toBeVisible();
  }

  expect(requests.some((request) => [
    "/credit-applications/",
    "/documents/",
    "/document-categories/",
    "/collection-cases/",
  ].includes(request.path))).toBe(false);
});

test("les deux types de caution bloquent les champs obligatoires avant envoi", async ({ page }) => {
  const user = makeUser(["sureties.view_surety", "sureties.add_surety"]);
  const { requests } = await installApiMocks(page, { user });
  await page.addInitScript((id) => {
    localStorage.setItem("finflow_access", "e2e-access");
    localStorage.setItem("finflow_refresh", "e2e-refresh");
    localStorage.setItem("finflow_tenant", id);
  }, tenantId);
  await openPage(page, "/cautions");

  await expect(page.getByRole("heading", { name: "Cautions", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Nouvelle caution" }).click();
  const save = page.getByRole("button", { name: "Enregistrer la caution" });
  const lastName = page.getByRole("textbox", { name: "Nom *", exact: true });
  await expect(lastName).toHaveJSProperty("required", true);
  await save.click();
  expect(await lastName.evaluate((input) => (input as HTMLInputElement).checkValidity())).toBe(false);
  expect(requests.some((request) => request.path === "/sureties/" && request.method === "POST")).toBe(false);

  await page.getByRole("button", { name: "Entreprise", exact: true }).click();
  const companyName = page.getByRole("textbox", { name: /Raison sociale/ });
  await expect(companyName).toHaveJSProperty("required", true);
  await save.click();
  expect(await companyName.evaluate((input) => (input as HTMLInputElement).checkValidity())).toBe(false);
  expect(requests.some((request) => request.path === "/sureties/" && request.method === "POST")).toBe(false);

  await companyName.fill("Entreprise E2E");
  const createSurety = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return url.pathname.endsWith("/sureties/") && request.method() === "POST";
  });
  await save.click();
  await createSurety;
  await expect(page.getByRole("button", { name: "Nouvelle caution" })).toBeVisible();
});

test("la permission de consultation des cautions ne donne pas le droit de création", async ({ page }) => {
  const user = makeUser(["sureties.view_surety"]);
  await installApiMocks(page, { user });
  await page.addInitScript((id) => {
    localStorage.setItem("finflow_access", "e2e-access");
    localStorage.setItem("finflow_refresh", "e2e-refresh");
    localStorage.setItem("finflow_tenant", id);
  }, tenantId);
  await openPage(page, "/cautions");

  await expect(page.getByRole("heading", { name: "Cautions", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Nouvelle caution" })).toHaveCount(0);
});

test("un engagement sélectionne une caution et transmet le montant et le type", async ({ page }) => {
  const user = makeUser([
    "credits.view_creditapplication", "sureties.view_surety", "sureties.add_surety",
  ]);
  await authenticateInBrowser(page, user);
  const surety = {
    id: "surety-e2e", display_name: "Entreprise de caution E2E", surety_type: "MORAL",
    activity: "Garantie commerciale", commitment_ceiling: "1000000",
    total_committed: "250000", available_ceiling: "750000",
  };
  await page.route(/\/api\/v1\/sureties\/(?=\?|$)/, async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({ json: paginated([surety]) });
      return;
    }
    await route.fallback();
  });
  let engagementPayload: Record<string, unknown> | null = null;
  await page.route(/\/api\/v1\/surety-engagements\/$/, async (route) => {
    if (route.request().method() === "POST") {
      engagementPayload = route.request().postDataJSON() as Record<string, unknown>;
      await route.fulfill({ json: { id: "engagement-e2e", ...engagementPayload } });
      return;
    }
    await route.fallback();
  });

  await openPage(page, "/dossiers/app-e2e/cautions/nouvelle");
  await expect(page.getByRole("heading", { name: "Ajouter une caution" })).toBeVisible();
  const suretySearch = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return url.pathname.endsWith("/sureties/") && url.searchParams.get("search") === "Entreprise";
  });
  await page.getByPlaceholder("Rechercher une caution existante…").fill("Entreprise");
  await suretySearch;
  await page.getByRole("button", { name: "Entreprise de caution E2E" }).click();
  await expect(page.getByRole("button", { name: "Changer" })).toBeVisible();
  await page.getByLabel("Montant engagé (XOF) *").fill("500000");
  await page.getByLabel("Type d'engagement").selectOption("SIMPLE");
  await page.getByLabel("Date de signature").fill("2026-10-20");

  const createResponse = page.waitForResponse((response) =>
    response.url().endsWith("/api/v1/surety-engagements/") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Rattacher la caution" }).click();
  await createResponse;
  await expect(page).toHaveURL(/\/dossiers\/app-e2e$/);
  expect(engagementPayload).toEqual({
    surety: surety.id, application: "app-e2e", amount: "500000",
    engagement_type: "SIMPLE", signed_date: "2026-10-20",
  });
});

test("la modification d'une caution envoie ses changements sans changer son type", async ({ page }) => {
  const user = makeUser(["sureties.view_surety", "sureties.change_surety"]);
  await authenticateInBrowser(page, user);
  const surety = {
    id: "surety-edit-e2e", display_name: "Entreprise caution recette", surety_type: "MORAL",
    company_name: "Entreprise caution recette", legal_form: "SARL", ifu: "IFU-E2E-01",
    rccm: "RCCM-E2E-01", activity: "Commerce", city: "Abidjan",
    commitment_ceiling: "1000000", additional_phones: [],
  };
  let updateBody = "";
  await page.route(/\/api\/v1\/sureties\/surety-edit-e2e\/$/, async (route) => {
    if (route.request().method() === "PATCH") {
      updateBody = (await route.request().postDataBuffer())?.toString("latin1") ?? "";
      await route.fulfill({ json: { ...surety, city: "Dakar" } });
      return;
    }
    if (route.request().method() === "GET") {
      await route.fulfill({ json: surety });
      return;
    }
    await route.fallback();
  });

  await openPage(page, "/cautions/surety-edit-e2e/modifier");
  await expect(page.getByRole("heading", { name: "Modifier — Entreprise caution recette" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Personne physique" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Entreprise", exact: true })).toBeDisabled();
  await page.getByRole("textbox", { name: "Ville", exact: true }).fill("Dakar");
  const updateResponse = page.waitForResponse((response) =>
    response.url().endsWith("/api/v1/sureties/surety-edit-e2e/")
      && response.request().method() === "PATCH",
  );
  await page.getByRole("button", { name: "Enregistrer les modifications" }).click();
  await updateResponse;
  await expect(page).toHaveURL(/\/cautions\/surety-edit-e2e$/);
  expect(updateBody).toContain('name="city"');
  expect(updateBody).toContain("Dakar");
  expect(updateBody).toContain('name="surety_type"');
  expect(updateBody).toContain("MORAL");
});

test("la modification d'une hypothèque envoie l'adresse actualisée sans changer le type", async ({ page }) => {
  const user = makeUser(["guarantees.view_guarantee", "guarantees.change_guarantee"]);
  await authenticateInBrowser(page, user);
  const guarantee = {
    id: "guarantee-edit-e2e", guarantee_type: "MORTGAGE", type_display: "Hypothèque",
    application: "app-e2e", client: clientFixture.id, reference: "GAR-E2E-EDIT",
    document_type: "LAND_TITLE", document_number: "TF-E2E-EDIT",
    document_issue_date: "2026-01-15", expertise_value: "1000000",
    expertise_date: "2026-01-15", expert_name: "Expert recette",
    value_to_consider: "900000", address: "Abidjan", is_insured: false,
    belongs_to_applicant: true,
  };
  let updateBody = "";
  await page.route(/\/api\/v1\/guarantees\/guarantee-edit-e2e\/$/, async (route) => {
    if (route.request().method() === "PATCH") {
      updateBody = (await route.request().postDataBuffer())?.toString("latin1") ?? "";
      await route.fulfill({ json: { ...guarantee, address: "Dakar" } });
      return;
    }
    if (route.request().method() === "GET") {
      await route.fulfill({ json: guarantee });
      return;
    }
    await route.fallback();
  });

  await openPage(page, "/garanties/guarantee-edit-e2e/modifier");
  await expect(page.getByRole("heading", { name: "Modifier la garantie" })).toBeVisible();
  await expect(page.getByLabel("Numéro du document *")).toHaveValue("TF-E2E-EDIT");
  await page.getByLabel("Adresse du bien").fill("Dakar");
  const updateResponse = page.waitForResponse((response) =>
    response.url().endsWith("/api/v1/guarantees/guarantee-edit-e2e/")
      && response.request().method() === "PATCH",
  );
  await page.getByRole("button", { name: "Enregistrer les modifications" }).click();
  await updateResponse;
  await expect(page).toHaveURL(/\/garanties\/guarantee-edit-e2e$/);
  expect(updateBody).toContain('name="guarantee_type"');
  expect(updateBody).toContain("MORTGAGE");
  expect(updateBody).toContain('name="address"');
  expect(updateBody).toContain("Dakar");
});

test("une main levée exige une garantie et un crédit soldé avant création", async ({ page }) => {
  const user = makeUser(["guarantees.initiate_guaranteereleaserequest"]);
  await installApiMocks(page, { user });
  await page.addInitScript((id) => {
    localStorage.setItem("finflow_access", "e2e-access");
    localStorage.setItem("finflow_refresh", "e2e-refresh");
    localStorage.setItem("finflow_tenant", id);
  }, tenantId);

  const client = {
    ...clientFixture, reference: "CLI-REL-01", cbs_client_id: "CBS-CLIENT-REL",
    display_name: "Client mainlevée",
  };
  const context = {
    client_id: client.id, client_display: client.display_name, cbs_client_id: client.cbs_client_id,
    guarantees: [{
      id: "guarantee-rel-e2e", reference: "GAR-REL-01", type_display: "Hypothèque",
      description: "Garantie de recette", current_value: "1500000", value_to_consider: "1500000",
      expertise_value: "1500000", status: "ACTIVE", process_busy: null,
    }],
    credits: [
      {
        application_id: "app-open-e2e", application_reference: "DOS-OUVERT-01",
        application_status_display: "Décaissé", product_label: "Crédit test", amount: "1500000",
        currency: "XOF", loan_id: "loan-open-e2e", loan_status_display: "Actif",
        cbs_loan_reference: "CBS-LOAN-OPEN", cbs_settled: false, cbs_outstanding: "300000",
        cbs_currency: "XOF", cbs_error: null, cbs_status_label: "En cours",
      },
      {
        application_id: "app-settled-e2e", application_reference: "DOS-SOLDE-01",
        application_status_display: "Décaissé", product_label: "Crédit test", amount: "1500000",
        currency: "XOF", loan_id: "loan-settled-e2e", loan_status_display: "Clôturé",
        cbs_loan_reference: "CBS-LOAN-SETTLED", cbs_settled: true, cbs_outstanding: "0",
        cbs_currency: "XOF", cbs_error: null, cbs_status_label: "Soldé",
      },
    ],
  };
  let createPayload: Record<string, unknown> | null = null;
  const created = {
    id: "release-e2e", reference: "ML-FIL01-0001", guarantee: "guarantee-rel-e2e",
    guarantee_reference: "GAR-REL-01", application: "app-settled-e2e", loan: "loan-settled-e2e",
    cbs_loan_reference: "CBS-LOAN-SETTLED", cbs_client_id: "CBS-CLIENT-REL",
    cbs_settled: true, cbs_outstanding: "0", cbs_currency: "XOF", cbs_raw: {},
    request_date: "2026-10-25", release_fees: "15000.50", fees: [],
    acte_status: "NONE", has_client_demande: false, has_generated_acte: false,
    has_signed_acte: false, can_deposit_signed_acte: true, status: "DRAFT",
    status_display: "Brouillon", comment: "Test fonctionnel", completed_at: null,
    client_display: client.display_name, created_at: "2026-10-25T10:00:00Z",
    updated_at: "2026-10-25T10:00:00Z",
  };
  await page.route(/\/api\/v1\/clients\//, async (route) => {
    await route.fulfill({ json: paginated([client]) });
  });
  await page.route(/\/api\/v1\/guarantee-releases\//, async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path.endsWith("/client-context/")) {
      await route.fulfill({ json: context });
    } else if (path === "/api/v1/guarantee-releases/" && request.method() === "POST") {
      createPayload = request.postDataJSON() as Record<string, unknown>;
      await route.fulfill({ json: created, status: 201 });
    } else if (path.endsWith("/release-e2e/") && request.method() === "GET") {
      await route.fulfill({ json: created });
    } else if (path.endsWith("/release-e2e/documents/")) {
      await route.fulfill({ json: [] });
    } else if (path.endsWith("/release-e2e/workflow/")) {
      await route.fulfill({ json: { instance: null } });
    } else {
      await route.fallback();
    }
  });

  await openPage(page, "/mains-levees/nouvelle");
  await page.getByPlaceholder("Matricule Core Banking, nom, dénomination ou référence…").fill("Client mainlevée");
  await page.locator(".client-ac .ac-item").click();
  await expect(page.getByText("2. Garantie à libérer")).toBeVisible();
  await page.locator('input[name="release-guarantee"]').check();
  await expect(page.locator('input[name="release-credit"]').nth(0)).toBeDisabled();
  const submit = page.getByRole("button", { name: "Créer le brouillon" });
  await expect(submit).toBeDisabled();

  await page.locator('input[name="release-credit"]').nth(1).check();
  await page.getByLabel("Frais de main levée").fill("15000.50");
  await page.getByLabel("Commentaire / motif").fill("Test fonctionnel");
  await expect(submit).toBeEnabled();
  const createRequest = page.waitForRequest((request) =>
    request.url().endsWith("/api/v1/guarantee-releases/") && request.method() === "POST",
  );
  await submit.click();
  await createRequest;
  expect(createPayload).toMatchObject({
    guarantee: "guarantee-rel-e2e", loan: "loan-settled-e2e",
    cbs_loan_reference: "CBS-LOAN-SETTLED", cbs_client_id: "CBS-CLIENT-REL",
    release_fees: "15000.50", as_draft: true, comment: "Test fonctionnel",
  });
  await expect(page).toHaveURL(/\/mains-levees\/release-e2e$/);
  await expect(page.getByText("ML-FIL01-0001")).toBeVisible();
});

test("l'analyse financière calcule les données saisies et enregistre la recommandation", async ({ page }) => {
  const user = makeUser([
    "credits.view_creditapplication", "credits.add_financialanalysis",
  ]);
  await installApiMocks(page, { user });
  await page.addInitScript((id) => {
    localStorage.setItem("finflow_access", "e2e-access");
    localStorage.setItem("finflow_refresh", "e2e-refresh");
    localStorage.setItem("finflow_tenant", id);
  }, tenantId);

  const application = {
    id: "app-e2e", reference: "DOS-E2E-001", client: clientFixture.id,
    client_display: clientFixture.display_name, client_reference: clientFixture.reference,
    client_type: "INDIVIDUAL", product: "product-e2e", product_label: "Crédit test",
    agency: "agency-e2e", amount_requested: "1000000", amount_proposed: "1000000",
    interest_rate: "12", fees_rate: "0", mandatory_savings_rate: "0",
    periodicity: "MONTHLY", duration_months: 12, first_due_date: null, last_due_date: null,
    repayment_mechanism: "DEGRESSIVE", purpose_type: "PERSONAL", purpose: "Trésorerie",
    currency: "XOF", dependents_count: 2, status: "DRAFT", status_display: "Brouillon",
    created_by: user.id, submitted_by: user.id,
  };
  const configuration = {
    context: { product: "product-e2e", agency: "agency-e2e", client_type: "INDIVIDUAL", individual_profile: "SALARIE" },
    policy: {}, thresholds: {},
    analysis: { required_fields: [], required_detail_tables: [], minimum_bank_statement_months: 0 },
    forms: { client_fields: [], analysis_fields: [], analysis_sections: [] },
    sources: [], origins: {}, fingerprint: "analysis-e2e", frozen: false,
    eligibility: { rules: [] },
    scoring: { grid: { engine: "LEGACY", missing_data: "RENORMALIZE", criteria: [], risk_cutoffs: [] } },
    pricing: { tariff: {}, product_defaults: {} },
  };
  let multipartBody = "";
  await page.route(/\/api\/v1\/credit-applications\/app-e2e\/$/, async (route) => {
    await route.fulfill({ json: application });
  });
  await page.route(/\/api\/v1\/credit-applications\/app-e2e\/configuration\//, async (route) => {
    await route.fulfill({ json: configuration });
  });
  await page.route(/\/api\/v1\/credit-applications\/app-e2e\/collateral-summary\//, async (route) => {
    await route.fulfill({
      json: {
        reference_amount: "1000000", currency: "XOF", guarantees: [],
        guarantees_gross_total: "0", guarantees_retained_total: "0",
        guarantee_coverage_pct: null, guarantee_gap: null,
        min_guarantee_coverage: "100", guarantee_ok: null, sureties: [],
        sureties_total: "0", surety_coverage_pct: null, requires_guarantee: false,
        alerts: [], haircuts: {},
      },
    });
  });
  await page.route(/\/api\/v1\/financial-analyses\//, async (route) => {
    if (route.request().method() === "POST") {
      multipartBody = route.request().postData() || "";
      await route.fulfill({ json: { id: "analysis-e2e", application: application.id }, status: 201 });
      return;
    }
    await route.fallback();
  });

  await openPage(page, "/dossiers/app-e2e/analyse-financiere");
  await expect(page.getByRole("heading", { name: "Nouvelle analyse financière" })).toBeVisible();
  await page.getByLabel("Date de l'analyse").fill("2026-10-01");
  await page.getByLabel("Salaire net (demandeur)").fill("800000");
  await page.getByLabel("Loyer / logement").fill("120000");
  await page.getByLabel("Recommandation (obligatoire pour soumettre)").selectOption("FAVORABLE");

  const createResponse = page.waitForResponse((response) =>
    response.url().endsWith("/api/v1/financial-analyses/") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Enregistrer l'analyse" }).click();
  await createResponse;
  const valueFor = (name: string) => multipartBody.match(
    new RegExp(`name="${name}"\\r\\n\\r\\n([^\\r\\n]*)`),
  )?.[1];
  expect(valueFor("application")).toBe(application.id);
  expect(valueFor("analysis_date")).toBe("2026-10-01");
  expect(valueFor("salary_income")).toBe("800000");
  expect(valueFor("rent_expense")).toBe("120000");
  expect(valueFor("recommendation")).toBe("FAVORABLE");
});

test("une dation transmet le bien additionnel, les frais et l'option de couverture", async ({ page }) => {
  const user = makeUser(["guarantees.initiate_dationrequest"]);
  await installApiMocks(page, { user });
  await page.addInitScript((id) => {
    localStorage.setItem("finflow_access", "e2e-access");
    localStorage.setItem("finflow_refresh", "e2e-refresh");
    localStorage.setItem("finflow_tenant", id);
  }, tenantId);

  const client = {
    ...clientFixture, reference: "CLI-DAT-01", cbs_client_id: "CBS-CLIENT-DAT",
    display_name: "Client dation",
  };
  let createPayload: Record<string, unknown> | null = null;
  const created = {
    id: "dation-e2e", reference: "DAT-FIL01-0001", client: client.id,
    client_display: client.display_name, application: null, application_reference: null,
    agency: null, cbs_client_id: client.cbs_client_id, cbs_total_outstanding: "1000000",
    cbs_currency: "XOF", cbs_checked_at: null, cbs_raw: {},
    asset_description: "Terrain agricole", asset_value: "1500000",
    assets: [{
      id: "dation-asset-e2e", source: "ADDITIONAL", source_display: "Bien additionnel",
      asset_type: "REAL_ESTATE", asset_type_display: "Immobilier", guarantee: null,
      guarantee_reference: null, guarantee_type_display: null, description: "Terrain agricole",
      value: "1500000", notes: "", created_at: "2026-10-25T10:00:00Z",
    }],
    fees: [{
      id: "dation-fee-e2e", fee_type: "NOTARY", fee_type_display: "Notaire / acte",
      label: "Acte notarié", amount: "25000", payer: "CLIENT", payer_display: "Client",
      fee_date: null, recoverable: true, notes: "", created_at: "2026-10-25T10:00:00Z",
    }],
    assets_total_value: "1500000", fees_client_total: "25000", fees_institution_total: "0",
    claim_to_cover: "1025000", residual_balance: "0", surplus_amount: "475000",
    require_full_coverage: true, settlement_notes: "", covers_claim: true, coverage_gap: "0",
    settlement: {
      assets_total: "1500000", claim: "1000000", fees_client_total: "25000",
      fees_institution_total: "0", claim_to_cover: "1025000", coverage_gap: "0",
      residual_balance: "0", surplus_amount: "475000", covers_claim: true,
    },
    status: "DRAFT", status_display: "Brouillon", comment: "Test dation",
    resulting_guarantee: null, completed_at: null, created_at: "2026-10-25T10:00:00Z",
    updated_at: "2026-10-25T10:00:00Z",
  };
  let detailDation = created;

  await page.route(/\/api\/v1\/clients\//, async (route) => {
    await route.fulfill({ json: paginated([client]) });
  });
  await page.route(/\/api\/v1\/dation-requests\//, async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path.endsWith("/preview-cbs/")) {
      await route.fulfill({
        json: { cbs_client_id: client.cbs_client_id, total_outstanding: "1000000", currency: "XOF", breakdown: [] },
      });
    } else if (path === "/api/v1/dation-requests/" && request.method() === "POST") {
      createPayload = request.postDataJSON() as Record<string, unknown>;
      await route.fulfill({ json: created, status: 201 });
    } else if (path.endsWith("/dation-e2e/submit/") && request.method() === "POST") {
      detailDation = { ...detailDation, status: "IN_APPROVAL", status_display: "En validation" };
      await route.fulfill({ json: detailDation });
    } else if (path.endsWith("/dation-e2e/") && request.method() === "GET") {
      await route.fulfill({ json: detailDation });
    } else if (path.endsWith("/dation-e2e/documents/")) {
      await route.fulfill({ json: [] });
    } else if (path.endsWith("/dation-e2e/workflow/")) {
      await route.fulfill({ json: { instance: null } });
    } else {
      await route.fallback();
    }
  });

  await openPage(page, "/dations/nouvelle");
  await page.getByPlaceholder("Matricule Core Banking, nom, dénomination ou référence…").fill("Client dation");
  await page.locator(".client-ac .ac-item").click();
  await expect(page.getByText("Créance CBS", { exact: true })).toBeVisible();
  await expect(page.locator(".dation-coverage-metrics")).toContainText(/1.*000.*000/);

  await page.getByRole("button", { name: "Ajouter", exact: true }).first().click();
  await page.getByLabel("Description du bien").fill("Terrain agricole");
  await page.getByLabel("Type").selectOption("REAL_ESTATE");
  await page.getByLabel("Valeur retenue").fill("1500000");
  await page.getByRole("button", { name: "Ajouter", exact: true }).nth(1).click();
  await page.getByLabel("Libellé").fill("Acte notarié");
  await page.getByLabel("Montant").fill("25000");
  await page.getByLabel("Payeur").selectOption("CLIENT");
  await page.getByLabel("Note").fill("Test dation");
  await page.getByLabel("Exiger la couverture intégrale à la soumission du circuit").check();

  const createRequest = page.waitForRequest((request) =>
    request.url().endsWith("/api/v1/dation-requests/") && request.method() === "POST",
  );
  await page.getByRole("button", { name: "Créer le brouillon" }).click();
  await createRequest;
  expect(createPayload).toEqual({
    client: client.id, application: null, cbs_client_id: client.cbs_client_id,
    as_draft: true, require_full_coverage: true, guarantee_ids: [],
    additional_assets: [{ description: "Terrain agricole", value: "1500000", asset_type: "REAL_ESTATE" }],
    fees: [{ fee_type: "NOTARY", label: "Acte notarié", amount: "25000", payer: "CLIENT" }],
    comment: "Test dation",
  });
  await expect(page).toHaveURL(/\/dations\/dation-e2e$/);
  await expect(page.getByText("DAT-FIL01-0001")).toBeVisible();
  const submitResponse = page.waitForResponse((response) =>
    response.url().endsWith("/api/v1/dation-requests/dation-e2e/submit/")
      && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Soumettre au circuit" }).click();
  await submitResponse;
  await expect(page.locator(".client-banner-meta").getByText("En validation", { exact: true })).toBeVisible();
});

test("une formalisation sélectionne la garantie du dossier puis crée son brouillon", async ({ page }) => {
  const user = makeUser(["guarantees.initiate_guaranteeformalizationrequest"]);
  await installApiMocks(page, { user });
  await page.addInitScript((id) => {
    localStorage.setItem("finflow_access", "e2e-access");
    localStorage.setItem("finflow_refresh", "e2e-refresh");
    localStorage.setItem("finflow_tenant", id);
  }, tenantId);

  const guarantee = {
    id: "guarantee-form-e2e", reference: "GAR-FORM-01", application: "app-e2e",
    type_display: "Hypothèque", description: "Garantie pour formalisation",
    current_value: "500000", status: "ACTIVE", formalization_busy: false,
    process_busy: null,
  };
  const created = {
    id: "formalization-e2e", reference: "FOR-FIL01-0001",
    guarantee: guarantee.id, guarantee_reference: guarantee.reference,
    client: clientFixture.id, client_display: clientFixture.display_name,
    application: "app-e2e", application_reference: "DOS-E2E-001", agency: null,
    status: "DRAFT", status_display: "Brouillon", legal_stage: "NOT_SENT",
    legal_stage_display: "Non soumis chez le notaire", notary_name: "Étude Test",
    notary_reference: "NOT-001", sent_to_notary_at: null, expected_return_date: null,
    registration_number: "", registration_date: null, registration_authority: "",
    comment: "Test formalisation", completed_at: null, fees: [],
    created_at: "2026-10-25T10:00:00Z", updated_at: "2026-10-25T10:00:00Z",
  };
  let createPayload: Record<string, unknown> | null = null;
  let addFeePayload: Record<string, unknown> | null = null;
  await page.route(/\/api\/v1\/guarantee-formalizations\//, async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path.endsWith("/compose-context/")) {
      await route.fulfill({
        json: {
          client_id: clientFixture.id,
          client_display: clientFixture.display_name,
          application_id: "app-e2e",
          application_reference: "DOS-E2E-001",
          credits: [],
          guarantees: [guarantee],
        },
      });
    } else if (path === "/api/v1/guarantee-formalizations/" && request.method() === "POST") {
      createPayload = request.postDataJSON() as Record<string, unknown>;
      await route.fulfill({ json: created, status: 201 });
    } else if (path.endsWith("/formalization-e2e/add-fee/") && request.method() === "POST") {
      addFeePayload = request.postDataJSON() as Record<string, unknown>;
      await route.fulfill({ json: { id: "fee-form-e2e", ...addFeePayload } });
    } else if (path.endsWith("/formalization-e2e/") && request.method() === "GET") {
      await route.fulfill({ json: created });
    } else if (path.endsWith("/formalization-e2e/documents/")) {
      await route.fulfill({ json: [] });
    } else if (path.endsWith("/formalization-e2e/workflow/")) {
      await route.fulfill({ json: { instance: null } });
    } else {
      await route.fallback();
    }
  });

  await openPage(page, "/formalisations/nouvelle?application=app-e2e");
  await expect(page.getByText("2. Garantie à formaliser")).toBeVisible();
  await expect(page.locator('input[name="formalization-guarantee"]')).toBeChecked();
  await page.getByLabel("Notaire / étude").fill("Étude Test");
  await page.getByLabel("Réf. dossier notaire").fill("NOT-001");
  await page.getByLabel("Commentaire").fill("Test formalisation");
  const createRequest = page.waitForRequest((request) =>
    request.url().endsWith("/api/v1/guarantee-formalizations/") && request.method() === "POST",
  );
  await page.getByRole("button", { name: "Mettre dans le circuit" }).click();
  await createRequest;
  expect(createPayload).toEqual({
    guarantee: guarantee.id, notary_name: "Étude Test", notary_reference: "NOT-001",
    comment: "Test formalisation", as_draft: true,
  });
  await expect(page).toHaveURL(/\/formalisations\/formalization-e2e$/);
  await expect(page.getByText("FOR-FIL01-0001")).toBeVisible();
  await page.getByLabel("Montant", { exact: true }).fill("18000");
  await page.getByLabel("Libellé").fill("Frais d'enregistrement");
  const addFeeResponse = page.waitForResponse((response) =>
    response.url().endsWith("/api/v1/guarantee-formalizations/formalization-e2e/add-fee/")
      && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Ajouter frais" }).click();
  await addFeeResponse;
  expect(addFeePayload).toEqual({
    fee_type: "NOTARY", label: "Frais d'enregistrement", amount: "18000", payer: "CLIENT",
  });
});

test("l'édition client impose le nom selon le type puis enregistre le dossier complet", async ({ page }) => {
  const user = makeUser(["clients.change_client"]);
  const { requests } = await installApiMocks(page, { user });
  await page.addInitScript((id) => {
    localStorage.setItem("finflow_access", "e2e-access");
    localStorage.setItem("finflow_refresh", "e2e-refresh");
    localStorage.setItem("finflow_tenant", id);
  }, tenantId);
  await openPage(page, "/clients/client-e2e/modifier");

  await expect(page.getByRole("heading", { name: "Modifier — Awa Koné E2E" })).toBeVisible();
  const save = page.getByRole("button", { name: "Enregistrer les modifications" });
  const lastName = page.getByRole("textbox", { name: "Nom *", exact: true });
  await expect(lastName).toHaveJSProperty("required", true);
  await lastName.fill("");
  await save.click();
  expect(await lastName.evaluate((input) => (input as HTMLInputElement).checkValidity())).toBe(false);
  expect(requests.some((request) => request.path === "/clients/client-e2e/" && request.method === "PATCH")).toBe(false);

  await lastName.fill("Koné");
  await page.getByRole("button", { name: "Personne morale", exact: true }).click();
  const companyName = page.getByRole("textbox", { name: /Raison sociale/ });
  await expect(companyName).toHaveJSProperty("required", true);
  await companyName.fill("");
  await save.click();
  expect(await companyName.evaluate((input) => (input as HTMLInputElement).checkValidity())).toBe(false);
  expect(requests.some((request) => request.path === "/clients/client-e2e/" && request.method === "PATCH")).toBe(false);

  await companyName.fill("Client E2E SARL");
  const updateRequest = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return url.pathname.endsWith("/clients/client-e2e/") && request.method() === "PATCH";
  });
  await save.click();
  await updateRequest;
  await expect(page).toHaveURL(/\/clients\/client-e2e$/);
});

test("les modules principaux s'ouvrent et la configuration montre un état vide exploitable", async ({ page }) => {
  await installApiMocks(page);
  await page.addInitScript((id) => {
    localStorage.setItem("finflow_access", "e2e-access");
    localStorage.setItem("finflow_refresh", "e2e-refresh");
    localStorage.setItem("finflow_tenant", id);
  }, tenantId);
  await openPage(page, "/clients");
  await expect(page.getByRole("heading", { name: "Clients" })).toBeVisible();
  const sidebarToggle = page.locator(".sidebar-toggle.desktop-only");
  if (await sidebarToggle.getAttribute("aria-label") === "Déployer le menu") {
    await sidebarToggle.click();
  }

  const journeys = [
    {
      link: "Dossiers de crédit",
      heading: "Dossiers de crédit",
      endpoint: "/credit-applications/",
      search: "Réf. dossier, client…",
      empty: "Aucun dossier ne correspond à ces critères.",
    },
    {
      link: "Mes validations",
      heading: "Mes validations",
      endpoint: "/approval-tasks/my_dossiers/",
      search: "Référence, client, produit, initiateur, étape…",
      empty: "Aucun dossier en circuit pour votre périmètre.",
    },
    {
      link: "Prêts",
      heading: "Prêts",
      endpoint: "/loans/",
      search: "Réf. dossier, client, CBS…",
      empty: "Aucun prêt pour cette filiale.",
    },
    {
      link: "Garanties",
      heading: "Garanties",
      endpoint: "/guarantees/",
      search: "Référence, client, propriétaire…",
      empty: "Aucune garantie ne correspond à ces critères.",
    },
    {
      link: "Recouvrement",
      heading: "Recouvrement",
      endpoint: "/collection-cases/",
      search: "Référence, client, CBS…",
      empty: "Aucun crédit en impayé.",
    },
    {
      link: "GED",
      heading: "GED — Documents",
      endpoint: "/documents/",
      search: "Nom de fichier, catégorie, déposant…",
      empty: "Aucun document dans la GED pour ces filtres.",
    },
  ] as const;
  for (const journey of journeys) {
    const listRequest = page.waitForRequest((request) => {
      const url = new URL(request.url());
      return url.pathname.replace(/^\/api\/v1/, "") === journey.endpoint;
    });
    await page.getByRole("link", { name: journey.link, exact: true }).click();
    await expect(page.getByRole("heading", { name: journey.heading, exact: true })).toBeVisible();
    await listRequest;
    await expect(page.getByText(journey.empty, { exact: true })).toBeVisible();

    const searchValue = `recherche-${journey.link.toLowerCase().replaceAll(" ", "-")}`;
    const filteredRequest = page.waitForRequest((request) => {
      const url = new URL(request.url());
      return url.pathname.replace(/^\/api\/v1/, "") === journey.endpoint
        && url.searchParams.get("search") === searchValue;
    });
    await page.getByPlaceholder(journey.search).fill(searchValue);
    await filteredRequest;
  }

  const catalogueRequest = page.waitForRequest((request) =>
    new URL(request.url()).pathname.endsWith("/configuration-profiles/catalogue/"),
  );
  const profilesRequest = page.waitForRequest((request) =>
    new URL(request.url()).pathname.endsWith("/configuration-profiles/"),
  );
  await openPage(page, "/admin/configuration");
  await expect(page.getByRole("heading", { name: "Centre de configuration" })).toBeVisible();
  await expect(page.getByText("Aucun profil. La politique actuelle de la filiale s'applique.")).toBeVisible();
  await Promise.all([catalogueRequest, profilesRequest]);
});

test("la configuration permet de créer, simuler, soumettre puis publier avec un second administrateur", async ({ page }) => {
  const author = makeUser([
    ...modulePermissions,
    "configuration.change_configurationprofile",
    "configuration.preview_configurationprofile",
  ]);
  let currentUser = author;
  let profile: Record<string, any> | null = null;
  const configurationCalls: { path: string; method: string; body?: Record<string, any> }[] = [];
  await authenticateInBrowser(page, author);

  await page.route("**/api/v1/users/me/", async (route) => {
    await route.fulfill({ json: currentUser });
  });
  await page.route("**/api/v1/configuration-profiles/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace(/^\/api\/v1/, "");
    const method = request.method();
    const body = method === "GET" ? undefined : request.postDataJSON() as Record<string, any>;
    configurationCalls.push({ path, method, body });

    if (path === "/configuration-profiles/catalogue/") {
      await route.fulfill({ json: {
        default_exposure: {
          enabled: false, currency: "XOF", gate: "SUBMIT", include_pending: false,
          client_limit: null, group_limit: null, maximum_age_days: 0,
          require_verified_snapshot: true, use_cbs_client_limit: false,
        },
        default_simulation: {
          engine: "LEGACY", day_count: "ACT365_FIXED", amount_step: "10",
          rounding: "HALF_UP", due_adjustment: "NONE", interest_dates: "NOMINAL", calendar: null,
        },
        default_forms: { client_fields: [], analysis_fields: [], analysis_sections: [] },
        default_kyc: { required_fields: [], required_documents: [], check_expiry: false, validity_days: 0 },
        default_references: { civility: [], marital_status: [], id_document_type: [], legal_form: [] },
        form_sections: [], kyc_fields: [], kyc_documents: [],
        policy: [{ key: "approval_validity_days", label: "Validité de l'accord", type: "integer", choices: [], default: 30, operational: false }],
        thresholds: [], analysis_fields: [{ key: "income", label: "Revenus" }], detail_tables: [],
        precedence: ["Groupe", "Filiale", "Produit", "Agence"], locked_rules: [], modules: [],
        eligibility_criteria: [], score_metrics: [],
        default_grid: { engine: "LEGACY", missing_data: "RENORMALIZE", criteria: [], risk_cutoffs: ["80", "60", "40", "20"] },
        default_tariff: {
          engine: "LEGACY", currency: "XOF",
          interest_rate: { default: null, min: null, max: null, negotiable: false },
          fees_rate: { default: null, min: null, max: null, negotiable: false },
          mandatory_savings_rate: { default: null, min: null, max: null, negotiable: false },
          allow_manual_fees: true, max_total_fees_pct: null, processing_tax_rate: "0", bands: [], charges: [],
        },
      } });
      return;
    }
    if (path === "/configuration-profiles/" && method === "GET") {
      await route.fulfill({ json: paginated(profile ? [profile] : []) });
      return;
    }
    if (path === "/configuration-profiles/" && method === "POST") {
      const payload = body || {};
      profile = {
        ...payload, id: "profile-e2e", version: 1, status: "DRAFT",
        product_label: "", agency_label: "", updated_at: "2026-10-25T10:00:00Z",
        updated_by_display: author.username, published_by_display: "", published_at: null,
        retirement_reason: "", created_by_id: author.id, updated_by_id: author.id,
      };
      await route.fulfill({ status: 201, json: profile });
      return;
    }
    if (path === "/configuration-profiles/profile-e2e/" && method === "PATCH" && profile) {
      const { expected_updated_at: _expectedUpdatedAt, ...payload } = body || {};
      profile = {
        ...profile, ...payload, updated_at: "2026-10-25T11:00:00Z",
        updated_by_id: currentUser.id, updated_by_display: currentUser.username,
      };
      await route.fulfill({ json: profile });
      return;
    }
    const actionMatch = path.match(/^\/configuration-profiles\/profile-e2e\/(preview|submit|publish)\/$/);
    if (actionMatch && profile) {
      const action = actionMatch[1];
      if (action === "preview") {
        await route.fulfill({ json: {
          matches: true,
          before: {},
          after: {
            sources: [{ id: "profile-e2e", code: "config-e2e", name: "Configuration recette", version: 1 }],
            locked_keys: { "policy.approval_validity_days": "Groupe" },
            ignored_overrides: [],
            eligibility: { rules: [] },
            scoring: { grid: { engine: "LEGACY", criteria: [], risk_cutoffs: ["80", "60", "40", "20"] } },
            origins: { policy: { approval_validity_days: "Filiale" }, thresholds: {} },
            policy: { approval_validity_days: profile.overrides.policy.approval_validity_days }, thresholds: {},
          },
          changes: [{ section: "policy", key: "approval_validity_days", before: 30, after: profile.overrides.policy.approval_validity_days }],
          impact: { editable_matching: 2, frozen_matching: 0, note: "Aperçu sans modification des dossiers." },
        } });
        return;
      }
      if (action === "submit") {
        profile = { ...profile, status: "REVIEW" };
        await route.fulfill({ json: profile });
        return;
      }
      if (currentUser.id === profile.created_by_id || currentUser.id === profile.updated_by_id) {
        await route.fulfill({ status: 403, json: {
          detail: "La publication doit être effectuée par un autre utilisateur habilité que l'auteur et le dernier rédacteur.",
        } });
        return;
      }
      profile = { ...profile, status: "PUBLISHED", published_by_display: currentUser.username };
      await route.fulfill({ json: profile });
      return;
    }
    await route.fallback();
  });

  await openPage(page, "/admin/configuration");
  await expect(page.getByRole("heading", { name: "Centre de configuration" })).toBeVisible();
  await page.getByRole("button", { name: "Nouveau profil" }).click();
  await expect(page.locator(".card-title").filter({ hasText: "Nouveau profil" })).toBeVisible();

  await page.getByRole("button", { name: "Enregistrer le brouillon" }).click();
  expect(configurationCalls.filter((call) => call.path === "/configuration-profiles/" && call.method === "POST")).toHaveLength(0);
  await expect(page.getByLabel("Code stable")).toHaveJSProperty("required", true);

  await page.getByLabel("Code stable").fill("config-e2e");
  await page.getByLabel("Intitulé").fill("Configuration recette");
  await page.getByLabel("Type de client").selectOption("INDIVIDUAL");
  await page.getByLabel("Profil particulier").selectOption("SALARIE");
  await page.getByLabel("Motif de modification").fill("Recette interactive du paramétrage");
  await page.getByLabel(/Mois de relevés examinés/).fill("6");
  await page.getByRole("checkbox", { name: "Validité de l'accord" }).check();
  const policyValue = page.locator(".field").filter({ hasText: "Validité de l'accord" }).locator('input[type="number"]');
  await policyValue.fill("60");

  const createRequest = page.waitForRequest((request) =>
    new URL(request.url()).pathname.endsWith("/configuration-profiles/") && request.method() === "POST",
  );
  await page.getByRole("button", { name: "Enregistrer le brouillon" }).click();
  const saved = await createRequest;
  const savedPayload = saved.postDataJSON();
  expect(savedPayload.client_type).toBe("INDIVIDUAL");
  expect(savedPayload.individual_profile).toBe("SALARIE");
  expect(savedPayload.overrides.analysis.minimum_bank_statement_months).toBe(6);
  expect(savedPayload.overrides.policy.approval_validity_days).toBe(60);
  await expect(page.getByRole("status")).toContainText("Brouillon enregistré");

  await policyValue.fill("75");
  await expect(page.getByRole("button", { name: "Simuler le profil enregistré" })).toBeDisabled();
  const updateRequest = page.waitForRequest((request) =>
    new URL(request.url()).pathname.endsWith("/profile-e2e/") && request.method() === "PATCH",
  );
  await page.getByRole("button", { name: "Enregistrer le brouillon" }).click();
  const updated = await updateRequest;
  expect(updated.postDataJSON()).toMatchObject({
    expected_updated_at: "2026-10-25T10:00:00Z",
    overrides: { policy: { approval_validity_days: 75 }, analysis: { minimum_bank_statement_months: 6 } },
  });

  const previewRequest = page.waitForRequest((request) =>
    new URL(request.url()).pathname.endsWith("/profile-e2e/preview/") && request.method() === "POST",
  );
  await page.getByRole("button", { name: "Simuler le profil enregistré" }).click();
  const preview = await previewRequest;
  expect(preview.postDataJSON()).toMatchObject({ client_type: "INDIVIDUAL", individual_profile: "SALARIE" });
  await expect(page.getByText("Ce profil correspond au contexte simulé.")).toBeVisible();
  const changedPolicy = page.locator("details").filter({ hasText: "Modifications (1)" })
    .getByRole("row").filter({ hasText: "Validité de l'accord" });
  await expect(changedPolicy.getByRole("cell").nth(1)).toHaveText("30");
  await expect(changedPolicy.getByRole("cell").nth(2)).toHaveText("75");
  await expect(page.getByText(/2 dossier\(s\) modifiable\(s\)/)).toBeVisible();
  await expect(page.getByText(/Paramètres verrouillés par le Groupe/)).toBeVisible();

  const submitRequest = page.waitForRequest((request) =>
    new URL(request.url()).pathname.endsWith("/profile-e2e/submit/") && request.method() === "POST",
  );
  await page.getByRole("button", { name: "Soumettre à validation" }).click();
  await submitRequest;
  await expect(page.locator(".card-title").filter({ hasText: "Configuration recette — v1 — À valider" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Publier" })).toHaveCount(0);

  currentUser = makeUser([
    ...modulePermissions,
    "configuration.change_configurationprofile",
    "configuration.preview_configurationprofile",
    "configuration.publish_configurationprofile",
  ]);
  currentUser.id = "reviewer-e2e";
  currentUser.username = "e2e-reviewer";
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "Centre de configuration" })).toBeVisible();
  await page.getByRole("button", { name: "Ouvrir" }).click();
  const publishRequest = page.waitForRequest((request) =>
    new URL(request.url()).pathname.endsWith("/profile-e2e/publish/") && request.method() === "POST",
  );
  await page.getByRole("button", { name: "Publier" }).click();
  const published = await publishRequest;
  await expect(page.locator(".card-title").filter({ hasText: "Configuration recette — v1 — Publié" })).toBeVisible();
  expect(configurationCalls.find((call) => call.path.endsWith("/publish/"))?.method).toBe("POST");
  expect(published.postDataJSON()).toEqual({});
  expect(profile?.published_by_display).toBe("e2e-reviewer");
});

test("l'administrateur Groupe peut basculer sur le socle partagé", async ({ page }) => {
  const groupUser = makeUser(modulePermissions);
  groupUser.is_group_level = true;
  groupUser.is_staff = true;
  groupUser.tenant = null;
  groupUser.capabilities = [];
  await authenticateInBrowser(page, groupUser);

  await openPage(page, "/admin/configuration");
  await expect(page.getByText("Périmètre : Filiale sélectionnée.")).toBeVisible();
  const groupProfilesRequest = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return request.method() === "GET"
      && url.pathname.endsWith("/configuration-profiles/")
      && url.searchParams.get("scope") === "group";
  });
  const groupCatalogueRequest = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return url.pathname.endsWith("/configuration-profiles/catalogue/")
      && url.searchParams.get("scope") === "group";
  });
  await page.getByRole("checkbox", { name: "Administrer le socle Groupe" }).check();
  const [profiles, catalogue] = await Promise.all([groupProfilesRequest, groupCatalogueRequest]);
  expect(new URL(profiles.url()).searchParams.get("scope")).toBe("group");
  expect(new URL(catalogue.url()).searchParams.get("scope")).toBe("group");
  await expect(page.getByText("Périmètre : Groupe — applicable à toutes les filiales.")).toBeVisible();
});

test("le formulaire de dossier adapte l'objet CBS au mode local", async ({ page }) => {
  await authenticateInBrowser(page, makeUser(modulePermissions));
  await openPage(page, "/dossiers/nouveau");
  await expect(page.getByRole("heading", { name: "Nouveau dossier de crédit" })).toBeVisible();

  const clientSearch = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return url.pathname.endsWith("/clients/") && url.searchParams.get("search") === "E2E";
  });
  await page.getByPlaceholder("Matricule Core Banking, nom, dénomination ou référence…").fill("E2E");
  await clientSearch;
  await page.getByRole("button", { name: /Awa Koné E2E/ }).click();
  await page.getByLabel("Type de crédit").selectOption("product-e2e");

  const financingObject = page.getByLabel("Objet de financement CBS exact");
  await expect(financingObject).toHaveJSProperty("required", false);
  await expect(page.getByRole("status")).toContainText("Le champ est facultatif");
});

test("le dossier signale ses champs requis sans envoyer de requête incomplète", async ({ page }) => {
  const { requests } = await installApiMocks(page, { user: makeUser(modulePermissions) });
  await page.addInitScript((id) => {
    localStorage.setItem("finflow_access", "e2e-access");
    localStorage.setItem("finflow_refresh", "e2e-refresh");
    localStorage.setItem("finflow_tenant", id);
  }, tenantId);
  await openPage(page, "/dossiers/nouveau");

  await expect(page.getByPlaceholder("Matricule Core Banking, nom, dénomination ou référence…"))
    .toHaveJSProperty("required", true);
  await expect(page.getByLabel("Type de crédit")).toHaveJSProperty("required", true);
  await expect(page.getByLabel("Montant demandé")).toHaveJSProperty("required", true);
  await expect(page.getByLabel("Durée du crédit (mois)")).toHaveJSProperty("required", true);

  await page.getByRole("button", { name: "Enregistrer le dossier" }).click();
  await expect(page.locator(".form-error")).toHaveText(
    "Veuillez renseigner les champs obligatoires : Client, Type de crédit, Montant demandé.",
  );
  expect(requests.some((request) => request.path === "/credit-applications/" && request.method === "POST"))
    .toBe(false);
});

test("la création d'un dossier transmet les paramètres et ouvre son détail", async ({ page }) => {
  await authenticateInBrowser(page, makeUser(modulePermissions));

  let createContentType = "";
  let createBody = "";
  await page.route(/\/api\/v1\/credit-applications\/$/, async (route) => {
    if (route.request().method() === "POST") {
      createContentType = route.request().headers()["content-type"] ?? "";
      createBody = (await route.request().postDataBuffer())?.toString("latin1") ?? "";
      await route.fulfill({
        json: {
          id: "app-created-e2e", reference: "DOS-E2E-NEW", client: clientFixture.id,
          client_display: clientFixture.display_name, status: "DRAFT", status_display: "Brouillon",
          amount_requested: "1500000", currency: "XOF",
        },
      });
      return;
    }
    await route.fallback();
  });

  await openPage(page, "/dossiers/nouveau");
  await page.getByPlaceholder("Matricule Core Banking, nom, dénomination ou référence…").fill("E2E");
  await page.getByRole("button", { name: /Awa Koné E2E/ }).click();
  await page.getByLabel("Type de crédit").selectOption("product-e2e");
  await page.getByLabel("Montant demandé").fill("1500000");
  await expect(page.getByText("Exigences applicables à la demande")).toBeVisible();

  const createResponse = page.waitForResponse((response) =>
    new URL(response.url()).pathname.endsWith("/credit-applications/")
      && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Enregistrer le dossier" }).click();
  await createResponse;
  await expect(page).toHaveURL(/\/dossiers\/app-created-e2e$/);

  expect(createContentType).toContain("multipart/form-data");
  for (const field of ["client", "product", "amount_requested", "duration_months", "document_checklist", "extra_fees"]) {
    expect(createBody).toContain(`name="${field}"`);
  }
  expect(createBody).toContain(clientFixture.id);
  expect(createBody).toContain("product-e2e");
  expect(createBody).toContain("1500000");
});

test("un brouillon de crédit modifiable transmet les changements", async ({ page }) => {
  await authenticateInBrowser(page, makeUser([...modulePermissions, "credits.change_creditapplication"]));
  let updateBody = "";
  await page.route(/\/api\/v1\/credit-applications\/app-e2e\/$/, async (route) => {
    if (route.request().method() === "PATCH") {
      updateBody = (await route.request().postDataBuffer())?.toString("latin1") ?? "";
      await route.fulfill({ json: { ...editableCreditFixture, amount_requested: "1750000" } });
      return;
    }
    if (route.request().method() === "GET") {
      await route.fulfill({ json: editableCreditFixture });
      return;
    }
    await route.fallback();
  });
  await page.route(/\/api\/v1\/credit-applications\/app-e2e\/configuration\/$/, async (route) => {
    await route.fulfill({
      json: {
        sources: [], financing_object_required: false,
        pricing: { tariff: { engine: "LEGACY", currency: "XOF", charges: [], allow_manual_fees: true } },
      },
    });
  });

  await openPage(page, "/dossiers/app-e2e/modifier");
  await expect(page.getByRole("heading", { name: "Modifier le dossier DOS-E2E-001" })).toBeVisible();
  await expect(page.getByText("Exigences applicables à la demande")).toBeVisible();
  await page.getByLabel("Montant demandé").fill("1750000");
  const updateResponse = page.waitForResponse((response) =>
    response.url().endsWith("/api/v1/credit-applications/app-e2e/")
      && response.request().method() === "PATCH",
  );
  await page.getByRole("button", { name: "Enregistrer les modifications" }).click();
  await updateResponse;
  await expect(page).toHaveURL(/\/dossiers\/app-e2e$/);
  expect(updateBody).toContain('name="amount_requested"');
  expect(updateBody).toContain("1750000");
});

test("un dossier de crédit approuvé reste en lecture seule à l'écran de modification", async ({ page }) => {
  await authenticateInBrowser(page, makeUser([...modulePermissions, "credits.change_creditapplication"]));
  await page.route(/\/api\/v1\/credit-applications\/app-e2e\/$/, async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({
        json: { ...editableCreditFixture, status: "APPROVED", status_display: "Approuvé" },
      });
      return;
    }
    await route.fallback();
  });

  await openPage(page, "/dossiers/app-e2e/modifier");
  await expect(page.getByRole("heading", { name: "Modifier le dossier DOS-E2E-001" })).toBeVisible();
  await expect(page.getByText(/Ce dossier ne peut plus être modifié/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Enregistrer les modifications" })).toHaveCount(0);
});

test("l'hypothèque valide ses informations et transmet ses justificatifs", async ({ page }) => {
  const user = makeUser([...modulePermissions, "guarantees.add_guarantee"]);
  const { requests } = await installApiMocks(page, { user });
  await page.addInitScript((id) => {
    localStorage.setItem("finflow_access", "e2e-access");
    localStorage.setItem("finflow_refresh", "e2e-refresh");
    localStorage.setItem("finflow_tenant", id);
  }, tenantId);
  let createBody = "";
  await page.route(/\/api\/v1\/guarantees\/$/, async (route) => {
    if (route.request().method() === "POST") {
      createBody = (await route.request().postDataBuffer())?.toString("latin1") ?? "";
      await route.fulfill({
        json: { id: "guarantee-created-e2e", application: "app-e2e", guarantee_type: "MORTGAGE" },
      });
      return;
    }
    await route.fallback();
  });
  await openPage(page, "/dossiers/app-e2e/garanties/nouvelle");
  await expect(page.getByRole("heading", { name: "Ajouter une garantie" })).toBeVisible();

  const save = page.getByRole("button", { name: "Enregistrer la garantie" });
  await save.click();
  await expect(page.locator(".form-error")).toHaveText(
    "Indiquez le type et le numéro du document pris en garantie.",
  );

  await page.getByLabel("Type de document").selectOption("LAND_TITLE");
  await page.getByLabel("Numéro du document").fill("TF-E2E-001");
  await save.click();
  await expect(page.locator(".form-error")).toHaveText("Indiquez la date d'établissement du document.");

  await page.getByLabel("Date d'établissement").fill("2026-01-15");
  await save.click();
  await expect(page.locator(".form-error")).toHaveText("Indiquez la valeur d'expertise.");

  await page.getByLabel("Valeur expertisée (XOF)").fill("1000000");
  await save.click();
  await expect(page.locator(".form-error")).toHaveText("Indiquez la date de l'expertise.");

  await page.getByLabel("Date de l'expertise").fill("2026-01-15");
  await save.click();
  await expect(page.locator(".form-error")).toHaveText("Indiquez l'expert ou le cabinet d'expertise.");
  await page.getByLabel("Nom de l'expert").fill("Expert recette");
  await page.getByLabel("Scan du document").setInputFiles({
    name: "titre-foncier-e2e.pdf", mimeType: "application/pdf", buffer: Buffer.from("titre recette"),
  });
  await page.getByLabel("Scan du rapport d'expertise").setInputFiles({
    name: "expertise-e2e.pdf", mimeType: "application/pdf", buffer: Buffer.from("expertise recette"),
  });
  expect(requests.some((request) => request.path === "/guarantees/" && request.method === "POST"))
    .toBe(false);
  const createResponse = page.waitForResponse((response) =>
    response.url().endsWith("/api/v1/guarantees/") && response.request().method() === "POST",
  );
  await save.click();
  await createResponse;
  await expect(page).toHaveURL(/\/dossiers\/app-e2e$/);
  expect(createBody).toContain('name="guarantee_type"');
  expect(createBody).toContain("MORTGAGE");
  expect(createBody).toContain("app-e2e");
  expect(createBody).toContain("TF-E2E-001");
  expect(createBody).toContain("2026-01-15");
  expect(createBody).toContain("1000000");
  expect(createBody).toContain("Expert recette");
  expect(createBody).toContain("titre-foncier-e2e.pdf");
  expect(createBody).toContain("expertise-e2e.pdf");
});

test("le gage véhicule exige son numéro de châssis", async ({ page }) => {
  const user = makeUser([...modulePermissions, "guarantees.add_guarantee"]);
  const { requests } = await installApiMocks(page, { user });
  await page.addInitScript((id) => {
    localStorage.setItem("finflow_access", "e2e-access");
    localStorage.setItem("finflow_refresh", "e2e-refresh");
    localStorage.setItem("finflow_tenant", id);
  }, tenantId);
  await openPage(page, "/dossiers/app-e2e/garanties/nouvelle");
  await expect(page.getByRole("heading", { name: "Ajouter une garantie" })).toBeVisible();

  await page.getByRole("button", { name: /Gage/ }).click();
  await expect(page.getByLabel("Type de document")).toHaveValue("REGISTRATION_CARD");
  await page.getByLabel("Numéro du document").fill("CG-E2E-001");
  await page.getByLabel("Date d'établissement").fill("2026-01-15");
  await page.getByLabel("Valeur expertisée (XOF)").fill("1000000");
  await page.getByLabel("Date de l'expertise").fill("2026-01-15");
  await page.getByLabel("Nom de l'expert").fill("Expert recette");
  await page.getByRole("button", { name: "Enregistrer la garantie" }).click();

  await expect(page.locator(".form-error")).toHaveText(
    "Le numéro de châssis est obligatoire pour un gage véhicule.",
  );
  expect(requests.some((request) => request.path === "/guarantees/" && request.method === "POST"))
    .toBe(false);
});

test("les erreurs de validation d'une garantie financière sont lisibles", async ({ page }) => {
  const user = makeUser([...modulePermissions, "guarantees.add_guarantee"]);
  const { requests } = await installApiMocks(page, {
    user,
    mutationErrors: { financial_type: ["Ce champ est obligatoire."] },
  });
  await page.addInitScript((id) => {
    localStorage.setItem("finflow_access", "e2e-access");
    localStorage.setItem("finflow_refresh", "e2e-refresh");
    localStorage.setItem("finflow_tenant", id);
  }, tenantId);
  await openPage(page, "/dossiers/app-e2e/garanties/nouvelle");
  await expect(page.getByRole("heading", { name: "Ajouter une garantie" })).toBeVisible();

  await page.getByRole("button", { name: /Garantie financière/ }).click();
  await page.getByRole("button", { name: "Enregistrer la garantie" }).click();
  await expect(page.locator(".form-error")).toHaveText(
    "Type de garantie financière : Ce champ est obligatoire.",
  );
  expect(requests.some((request) => request.path === "/guarantees/" && request.method === "POST"))
    .toBe(true);
});

test("le recouvrement bloque une promesse incomplète puis enregistre une promesse valide", async ({ page }) => {
  const user = makeUser([
    "collections.view_collectioncase",
    "collections.add_paymentpromise",
    "collections.add_collectionaction",
  ]);
  const { requests } = await installApiMocks(page, { user });
  await page.addInitScript((id) => {
    localStorage.setItem("finflow_access", "e2e-access");
    localStorage.setItem("finflow_refresh", "e2e-refresh");
    localStorage.setItem("finflow_tenant", id);
  }, tenantId);
  await openPage(page, "/recouvrement/case-e2e");

  await expect(page.getByRole("heading", { name: "Awa Koné E2E" })).toBeVisible();
  const amount = page.getByLabel("Montant", { exact: true });
  const date = page.getByLabel("Date promise", { exact: true });
  const save = page.getByRole("button", { name: "Enregistrer la promesse" });
  await expect(amount).toHaveJSProperty("required", true);
  await expect(date).toHaveJSProperty("required", true);

  await amount.fill("0");
  await date.fill("2026-11-25");
  expect(await amount.evaluate((input) => (input as HTMLInputElement).checkValidity())).toBe(false);
  await save.click();
  expect(requests.some((request) => request.path === "/payment-promises/" && request.method === "POST")).toBe(false);

  await amount.fill("25000");
  const promiseRequest = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return url.pathname.endsWith("/payment-promises/") && request.method() === "POST";
  });
  await save.click();
  await promiseRequest;
  await expect(page.getByText("Promesse de paiement enregistrée.", { exact: true })).toBeVisible();

  const actionForm = page.locator("form.inline-form").filter({
    has: page.getByRole("button", { name: "Ajouter l'action" }),
  });
  await actionForm.getByLabel("Résultat").fill("Client joint, échéance confirmée");
  await actionForm.getByLabel("Commentaire").fill("Relance téléphonique de recette");
  const actionResponse = page.waitForResponse((response) =>
    response.url().endsWith("/api/v1/collection-actions/")
      && response.request().method() === "POST",
  );
  await actionForm.getByRole("button", { name: "Ajouter l'action" }).click();
  const response = await actionResponse;
  expect(response.status()).toBe(200);
  const actionBody = response.request().postData() || "";
  expect(actionBody).toContain('name="case"');
  expect(actionBody).toContain("case-e2e");
  expect(actionBody).toContain("Client joint, échéance confirmée");
  expect(actionBody).toContain("Relance téléphonique de recette");
  await expect(page.getByText("Action de relance enregistrée.", { exact: true })).toBeVisible();
});

test("la GED combine ses filtres et permet de les réinitialiser", async ({ page }) => {
  const user = makeUser(["documents.view_document"]);
  await installApiMocks(page, { user });
  await page.addInitScript((id) => {
    localStorage.setItem("finflow_access", "e2e-access");
    localStorage.setItem("finflow_refresh", "e2e-refresh");
    localStorage.setItem("finflow_tenant", id);
  }, tenantId);

  const initialDocuments = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return url.pathname.endsWith("/documents/") && !url.searchParams.has("related_kind");
  });
  await openPage(page, "/documents");
  await expect(page.getByRole("heading", { name: "GED — Documents" })).toBeVisible();
  await initialDocuments;
  await expect(page.getByText("Aucun document dans la GED pour ces filtres.", { exact: true })).toBeVisible();

  const moduleFilter = page.getByRole("combobox", { name: "Module", exact: true });
  const moduleRequest = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return url.pathname.endsWith("/documents/") && url.searchParams.get("related_kind") === "COLLECTION";
  });
  await moduleFilter.selectOption("COLLECTION");
  await moduleRequest;

  const searchRequest = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return url.pathname.endsWith("/documents/")
      && url.searchParams.get("related_kind") === "COLLECTION"
      && url.searchParams.get("search") === "promesse-e2e";
  });
  await page.getByPlaceholder("Nom de fichier, catégorie, déposant…").fill("promesse-e2e");
  await searchRequest;

  await page.getByRole("button", { name: "Réinitialiser" }).click();
  await expect(moduleFilter).toHaveValue("");
  await expect(page.getByPlaceholder("Nom de fichier, catégorie, déposant…")).toHaveValue("");
  await expect(page.getByText("Aucun document dans la GED pour ces filtres.", { exact: true })).toBeVisible();
});

test("la GED vérifie ou rejette un document avec son commentaire", async ({ page }) => {
  const user = makeUser(["documents.view_document", "documents.change_document"]);
  await authenticateInBrowser(page, user);
  const statuses: Record<string, string> = {
    "doc-verify-e2e": "PENDING", "doc-reject-e2e": "PENDING",
  };
  const documents = [
    { id: "doc-verify-e2e", name: "justificatif-a-e2e.pdf" },
    { id: "doc-reject-e2e", name: "justificatif-b-e2e.pdf" },
  ].map((doc) => ({
    ...doc, category_code: "KYC", category_label: "Identité", related_kind: "CREDIT",
    related_type: "credits.creditapplication", object_id: "app-e2e",
    related_label: "DOS-E2E-001", size_bytes: 1024,
    created_at: "2026-10-25T10:00:00Z", expiry_date: null,
    file_url: null, file: null, verification_comment: "",
  }));
  await page.route(/\/api\/v1\/documents\/(?=\?|$)/, async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({
        json: paginated(documents.map((doc) => ({
          ...doc, verification_status: statuses[doc.id],
        }))),
      });
      return;
    }
    await route.fallback();
  });
  const verificationPayloads: Record<string, unknown>[] = [];
  await page.route(/\/api\/v1\/documents\/(doc-verify-e2e|doc-reject-e2e)\/verify\/$/, async (route) => {
    if (route.request().method() === "POST") {
      const id = new URL(route.request().url()).pathname.split("/").at(-3)!;
      const payload = route.request().postDataJSON() as Record<string, unknown>;
      verificationPayloads.push({ id, ...payload });
      statuses[id] = String(payload.status);
      await route.fulfill({ json: { id, ...payload, verification_status: payload.status } });
      return;
    }
    await route.fallback();
  });

  await openPage(page, "/documents");
  const verifiedRow = page.locator("tr").filter({ hasText: "justificatif-a-e2e.pdf" });
  const rejectedRow = page.locator("tr").filter({ hasText: "justificatif-b-e2e.pdf" });
  await expect(verifiedRow).toBeVisible();
  await expect(rejectedRow).toBeVisible();
  await expect(verifiedRow.getByRole("button", { name: "Vérifier" })).toBeDisabled();

  await verifiedRow.getByLabel("Commentaire de vérification").fill("Pièce conforme");
  const verifiedResponse = page.waitForResponse((response) =>
    response.url().endsWith("/documents/doc-verify-e2e/verify/")
      && response.request().method() === "POST",
  );
  await verifiedRow.getByRole("button", { name: "Vérifier" }).click();
  await verifiedResponse;
  await expect(verifiedRow.getByText("Vérifié", { exact: true })).toBeVisible();

  await rejectedRow.getByLabel("Commentaire de vérification").fill("Scan illisible");
  const rejectedResponse = page.waitForResponse((response) =>
    response.url().endsWith("/documents/doc-reject-e2e/verify/")
      && response.request().method() === "POST",
  );
  await rejectedRow.getByRole("button", { name: "Rejeter" }).click();
  await rejectedResponse;
  await expect(rejectedRow.getByText("Rejeté", { exact: true })).toBeVisible();
  expect(verificationPayloads).toEqual([
    { id: "doc-verify-e2e", status: "VERIFIED", comment: "Pièce conforme" },
    { id: "doc-reject-e2e", status: "REJECTED", comment: "Scan illisible" },
  ]);
});

test("un utilisateur Groupe sans filiale voit le périmètre requis sans charger les listes GED", async ({ page }) => {
  const user = {
    ...makeUser(["documents.view_document"]),
    tenant: null,
    is_group_level: true,
    data_scope: "GROUP" as const,
  };
  const { requests } = await installApiMocks(page, { user });
  await page.addInitScript(() => {
    localStorage.setItem("finflow_access", "e2e-access");
    localStorage.setItem("finflow_refresh", "e2e-refresh");
    localStorage.removeItem("finflow_tenant");
  });
  await openPage(page, "/documents");

  await expect(page.getByRole("heading", { name: "GED — Documents" })).toBeVisible();
  await expect(page.getByText(
    "Ce paramétrage est propre à une filiale. Sélectionnez une filiale dans la barre supérieure pour la gérer.",
    { exact: true },
  )).toBeVisible();
  expect(requests.some((request) => ["/documents/", "/document-categories/"].includes(request.path))).toBe(false);
});

test("le mode CBS exige un objet exact et explique un référentiel vide", async ({ page }) => {
  await installApiMocks(page, {
    user: makeUser(modulePermissions),
    financingObjectRequired: true,
  });
  await page.addInitScript((id) => {
    localStorage.setItem("finflow_access", "e2e-access");
    localStorage.setItem("finflow_refresh", "e2e-refresh");
    localStorage.setItem("finflow_tenant", id);
  }, tenantId);
  await openPage(page, "/dossiers/nouveau");

  const clientSearch = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return url.pathname.endsWith("/clients/") && url.searchParams.get("search") === "E2E";
  });
  await page.getByPlaceholder("Matricule Core Banking, nom, dénomination ou référence…").fill("E2E");
  await clientSearch;
  await page.getByRole("button", { name: /Awa Koné E2E/ }).click();
  await page.getByLabel("Type de crédit").selectOption("product-e2e");

  await expect(page.getByLabel("Objet de financement CBS exact")).toHaveJSProperty("required", true);
  await expect(page.getByRole("alert")).toContainText("aucun objet de financement actif");
});

test("le simulateur envoie ses paramètres et affiche l'échéancier retourné", async ({ page }) => {
  await authenticateInBrowser(page);
  await openPage(page, "/clients");
  await expect(page.getByRole("heading", { name: "Clients" })).toBeVisible();
  await page.getByRole("link", { name: "Simulateur", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Simulateur d'amortissement" })).toBeVisible();

  const simulationRequest = page.waitForRequest((request) =>
    request.url().includes("/credit-applications/simulate/") && request.method() === "POST",
  );
  await page.getByRole("button", { name: "Simuler l'échéancier" }).click();
  const request = await simulationRequest;
  expect(request.postDataJSON()).toMatchObject({
    amount: "1000000",
    annual_rate: "12.5",
    months: 12,
    periodicity: "MONTHLY",
    mechanism: "DEGRESSIVE",
  });
  await expect(page.getByText("1 échéance", { exact: false })).toBeVisible();
  await expect(page.getByText("Nombre d'échéances")).toBeVisible();
});

test("les prêts exposent un état de chargement avant le résultat", async ({ page }) => {
  await authenticateInBrowser(page);

  let releaseLoans!: () => void;
  const loansResponse = new Promise<void>((resolve) => {
    releaseLoans = resolve;
  });
  await page.route("**/api/v1/loans/**", async (route) => {
    await loansResponse;
    await route.fulfill({ json: paginated([]) });
  });

  await openPage(page, "/clients");
  await expect(page.getByRole("heading", { name: "Clients" })).toBeVisible({ timeout: 15_000 });
  await page.getByRole("link", { name: "Prêts", exact: true }).click();
  await expect(page.getByLabel("Chargement")).toBeVisible();

  releaseLoans();
  await expect(page.getByText("Aucun prêt pour cette filiale.", { exact: true })).toBeVisible();
});

test("la page Rôles affiche l'erreur puis récupère après une nouvelle tentative", async ({ page }) => {
  const user = makeUser(["accounts.view_tenantrole"]);
  const api = await installApiMocks(page, {
    user,
    // React Query retries failed requests automatically before showing its
    // error state; keep the endpoint unavailable until the user retries.
    failures: { "/roles/options/": Number.MAX_SAFE_INTEGER },
  });
  await page.addInitScript((id) => {
    localStorage.setItem("finflow_access", "e2e-access");
    localStorage.setItem("finflow_refresh", "e2e-refresh");
    localStorage.setItem("finflow_tenant", id);
  }, tenantId);
  await openPage(page, "/admin/roles");

  await expect(page.getByRole("alert")).toContainText(
    "Impossible de charger les rôles de cette filiale.",
    { timeout: 15_000 },
  );
  api.clearFailure("/roles/options/");
  const retry = page.getByRole("button", { name: "Réessayer" });
  await retry.focus();
  await expect(retry).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByText("Aucun rôle pour cette filiale.")).toBeVisible();
  expect(api.requests.some((request) => request.path === "/permissions/")).toBe(false);
});

test("la création d'utilisateur respecte l'agence et le périmètre choisis", async ({ page }) => {
  const user = makeUser(["accounts.view_user", "accounts.change_user", "accounts.add_user"]);
  await installApiMocks(page, { user });
  await page.addInitScript((id) => {
    localStorage.setItem("finflow_access", "e2e-access");
    localStorage.setItem("finflow_refresh", "e2e-refresh");
    localStorage.setItem("finflow_tenant", id);
  }, tenantId);

  const agency = {
    id: "agency-e2e", tenant: tenantId, code: "AG-E2E", name: "Agence recette",
    region: "Nord", address: "", is_active: true, manager_last_name: "",
    manager_first_name: "", manager_phone: "",
  };
  await page.route(/\/api\/v1\/agencies\//, async (route) => {
    await route.fulfill({ json: paginated([agency]) });
  });

  let createPayload: Record<string, unknown> | null = null;
  await page.route("**/api/v1/users/", async (route) => {
    if (route.request().method() === "POST") {
      createPayload = route.request().postDataJSON() as Record<string, unknown>;
      await route.fulfill({ json: { id: "new-user-e2e", ...createPayload } });
      return;
    }
    await route.fallback();
  });

  await openPage(page, "/admin/utilisateurs");
  await expect(page.getByRole("heading", { name: "Utilisateurs" })).toBeVisible();
  await page.getByRole("button", { name: "Nouvel utilisateur" }).click();
  await page.getByLabel("Identifiant *").fill("agent-e2e");
  await page.getByLabel(/E-mail/).fill("agent-e2e@example.test");
  await page.getByLabel("Agence principale *").selectOption(agency.id);

  const createRequest = page.waitForRequest((request) =>
    request.url().endsWith("/api/v1/users/") && request.method() === "POST",
  );
  await page.getByRole("button", { name: "Créer l'utilisateur" }).click();
  await createRequest;

  expect(createPayload).toMatchObject({
    username: "agent-e2e", email: "agent-e2e@example.test", tenant: tenantId,
    agency: agency.id, agency_ids: [agency.id], data_scope: "AGENCY", password_delivery: "email",
  });
  await expect(page.getByText("Utilisateur créé.")).toBeVisible();
});

test("une agence exige son code et son nom, puis transmet ses paramètres", async ({ page }) => {
  const user = makeUser(["tenants.view_agency", "tenants.change_agency", "tenants.add_agency"]);
  await installApiMocks(page, { user });
  await page.addInitScript((id) => {
    localStorage.setItem("finflow_access", "e2e-access");
    localStorage.setItem("finflow_refresh", "e2e-refresh");
    localStorage.setItem("finflow_tenant", id);
  }, tenantId);

  let createPayload: Record<string, unknown> | null = null;
  await page.route("**/api/v1/agencies/", async (route) => {
    if (route.request().method() === "POST") {
      createPayload = route.request().postDataJSON() as Record<string, unknown>;
      await route.fulfill({ json: { id: "agency-new-e2e", ...createPayload } });
      return;
    }
    await route.fulfill({ json: paginated([]) });
  });

  await openPage(page, "/admin/agences");
  await expect(page.getByRole("heading", { name: "Agences" })).toBeVisible();
  await page.getByRole("button", { name: "Nouvelle agence" }).click();
  const code = page.getByLabel("Code *");
  const name = page.getByLabel("Nom *");
  await expect(code).toHaveJSProperty("required", true);
  await expect(name).toHaveJSProperty("required", true);
  await page.getByRole("button", { name: "Créer l'agence" }).click();
  expect(createPayload).toBeNull();

  await code.fill("AG-E2E-02");
  await name.fill("Agence test fonctionnel");
  await page.getByLabel("Région").fill("Centre");
  const createRequest = page.waitForRequest((request) =>
    request.url().endsWith("/api/v1/agencies/") && request.method() === "POST",
  );
  await page.getByRole("button", { name: "Créer l'agence" }).click();
  await createRequest;

  expect(createPayload).toMatchObject({
    code: "AG-E2E-02", name: "Agence test fonctionnel", region: "Centre", cbs_point_of_service_id: "",
  });
});

test("la gestion des filiales masque les actions sans droit de gestion", async ({ page }) => {
  const user = makeUser(["tenants.view_agency", "tenants.add_agency"]);
  user.tenant = null;
  user.is_group_level = true;
  user.is_staff = false;
  const api = await installApiMocks(page, { user });
  const tenant = {
    id: "tenant-group-e2e", code: "FIL01", name: "Filiale recette", country: "Côte d’Ivoire",
    zone: "Centre", currency: "XOF", timezone: "UTC", address: "", phone: "", email: "",
    is_active: true, brand_primary: "#173f5f", brand_accent: "#f6d55c",
    brand_sidebar: "#173f5f", brand_sidebar_text: "#ffffff", logo_url: null, officers: [],
  };
  await page.route("**/api/v1/tenants/", async (route) => {
    await route.fulfill({ json: paginated([tenant]) });
  });

  await page.addInitScript(() => {
    localStorage.setItem("finflow_access", "e2e-access");
    localStorage.setItem("finflow_refresh", "e2e-refresh");
    localStorage.removeItem("finflow_tenant");
  });
  await openPage(page, "/admin/filiales");
  await expect(page.getByRole("heading", { name: "Filiales" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Nouvelle filiale" })).toHaveCount(0);
  await page.getByRole("button", { name: /FIL01 — Filiale recette/ }).click();
  await expect(page.getByRole("button", { name: "Enregistrer la filiale" })).toHaveCount(0);
  await expect(page.getByText("La modification des filiales est réservée aux administrateurs Groupe.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Ajouter l'agence" })).toBeVisible();
  expect(api.requests.filter((request) => request.path === "/agencies/")).toHaveLength(1);
});

test("la configuration des filiales masque les agences sans droits d’accès", async ({ page }) => {
  const user = makeUser([]);
  user.tenant = null;
  user.is_group_level = true;
  user.is_staff = true;
  user.capabilities = [];
  const api = await installApiMocks(page, { user });
  const tenant = {
    id: "tenant-group-e2e", code: "FIL01", name: "Filiale recette", country: "Côte d’Ivoire",
    zone: "Centre", currency: "XOF", timezone: "UTC", address: "", phone: "", email: "",
    is_active: true, brand_primary: "#173f5f", brand_accent: "#f6d55c",
    brand_sidebar: "#173f5f", brand_sidebar_text: "#ffffff", logo_url: null, officers: [],
  };
  await page.route("**/api/v1/tenants/", async (route) => {
    await route.fulfill({ json: paginated([tenant]) });
  });
  await page.addInitScript(() => {
    localStorage.setItem("finflow_access", "e2e-access");
    localStorage.setItem("finflow_refresh", "e2e-refresh");
    localStorage.removeItem("finflow_tenant");
  });

  await openPage(page, "/admin/filiales");
  await page.getByRole("button", { name: /FIL01 — Filiale recette/ }).click();
  await expect(page.getByRole("button", { name: "Enregistrer la filiale" })).toBeVisible();
  await expect(page.getByText("La consultation des agences n’est pas autorisée.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Ajouter l'agence" })).toHaveCount(0);
  expect(api.requests.filter((request) => request.path === "/agencies/")).toEqual([]);
});

test("les écrans d'administration en lecture seule masquent toutes les actions d'écriture", async ({ page }) => {
  const user = makeUser([
    "accounts.view_user",
    "tenants.view_agency",
    "catalog.view_creditproduct",
    "catalog.view_productcategory",
    "workflow.view_workflowdefinition",
  ]);
  const { requests } = await installApiMocks(page, { user });
  await page.addInitScript((id) => {
    localStorage.setItem("finflow_access", "e2e-access");
    localStorage.setItem("finflow_refresh", "e2e-refresh");
    localStorage.setItem("finflow_tenant", id);
  }, tenantId);

  const agency = {
    id: "agency-readonly", tenant: tenantId, code: "AG-RO", name: "Agence lecture seule",
    region: "Nord", address: "", is_active: true, manager_last_name: "",
    manager_first_name: "", manager_phone: "",
  };
  const userRow = {
    id: "user-readonly", username: "compte-lecture", email: "lecture@example.test",
    tenant: tenantId, agency: agency.id, agency_ids: [agency.id], agencies_detail: [],
    data_scope: "TENANT", is_group_level: false, is_staff: false, is_superuser: false,
    is_active: true, groups: [],
  };
  const category = {
    id: "category-readonly", code: "MICRO", label: "Microcrédit", description: "",
    is_active: true,
  };
  const product = {
    id: "product-readonly", code: "PROD-RO", label: "Produit en lecture seule",
    category: category.id, category_label: category.label, client_type: "ALL",
    currency: "XOF", amount_min: "100000", amount_max: "5000000",
    duration_min_months: 3, duration_max_months: 24, interest_rate: "12",
    processing_fee_rate: "0", requires_guarantee: false, is_active: true,
  };
  await page.route(/\/api\/v1\/users\//, async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/users/") && route.request().method() === "GET") {
      await route.fulfill({ json: paginated([userRow]) });
    } else {
      await route.fallback();
    }
  });
  await page.route(/\/api\/v1\/agencies\//, async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/agencies/") && route.request().method() === "GET") {
      await route.fulfill({ json: paginated([agency]) });
    } else {
      await route.fallback();
    }
  });
  await page.route(/\/api\/v1\/product-categories\//, async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/product-categories/")) {
      await route.fulfill({ json: paginated([category]) });
    } else {
      await route.fallback();
    }
  });
  await page.route(/\/api\/v1\/credit-products\//, async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/credit-products/") && route.request().method() === "GET") {
      await route.fulfill({ json: paginated([product]) });
    } else {
      await route.fallback();
    }
  });

  await openPage(page, "/admin/utilisateurs");
  await expect(page.getByText("compte-lecture")).toBeVisible();
  await expect(page.getByRole("button", { name: "Nouvel utilisateur" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Modifier", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Actif" })).toHaveCount(0);

  await openPage(page, "/admin/agences");
  await expect(page.getByText("Agence lecture seule")).toBeVisible();
  await expect(page.getByRole("button", { name: "Nouvelle agence" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Modifier", exact: true })).toHaveCount(0);

  await openPage(page, "/admin/produits");
  await expect(page.getByText("Produit en lecture seule")).toBeVisible();
  await expect(page.getByRole("button", { name: "Nouveau produit" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Modifier", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Désactiver" })).toHaveCount(0);

  await openPage(page, "/admin/circuits");
  await expect(page.getByRole("heading", { name: "Circuits d'approbation" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Créer le circuit inactif" })).toHaveCount(0);
  expect(requests.filter((request) => request.method !== "GET")).toHaveLength(0);
});

test("un lecteur des connecteurs ne peut ni modifier ni déclencher une opération CBS", async ({ page }) => {
  const user = makeUser(["corebanking.view_corebankingconnector"]);
  const { requests } = await installApiMocks(page, { user });
  await page.addInitScript((id) => {
    localStorage.setItem("finflow_access", "e2e-access");
    localStorage.setItem("finflow_refresh", "e2e-refresh");
    localStorage.setItem("finflow_tenant", id);
  }, tenantId);

  await page.route(/\/api\/v1\/cbs-connectors\//, async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/cbs-connectors/") && route.request().method() === "GET") {
      await route.fulfill({ json: paginated([{
        id: "connector-readonly", name: "Connecteur lecture seule",
        protocol: "REST", base_url: "https://cbs.example.test", is_active: true,
        mapping_rules: {
          provider: "perfect", disbursement: { mode: "CBS" },
          endpoints: { authentification: "auth", crd_simple: "credit" },
        },
      }]) });
    } else {
      await route.fallback();
    }
  });

  await openPage(page, "/admin/connecteurs");
  await expect(page.getByRole("heading", { name: "Connecteurs Core Banking" })).toBeVisible();
  await expect(page.getByText("Connecteur lecture seule")).toBeVisible();
  await expect(page.getByRole("button", { name: "Nouveau connecteur Perfect" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Modifier", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Désactiver" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Test PING" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Importer les crédits" })).toHaveCount(0);
  expect(requests.some((request) => request.path === "/integration-logs/")).toBe(false);
  expect(requests.some((request) => request.path.startsWith("/cbs-connectors/") && request.method !== "GET")).toBe(false);
});

test("les rôles se créent et enregistrent les permissions et fonctions métier", async ({ page }) => {
  const user = makeUser([
    "accounts.view_tenantrole", "accounts.add_tenantrole", "accounts.change_tenantrole",
  ]);
  await installApiMocks(page, { user });
  await page.addInitScript((id) => {
    localStorage.setItem("finflow_access", "e2e-access");
    localStorage.setItem("finflow_refresh", "e2e-refresh");
    localStorage.setItem("finflow_tenant", id);
  }, tenantId);

  const role = { id: 3, name: "Analyste recette", permission_count: 0, user_count: 0 };
  const savePayloads: Record<string, unknown>[] = [];
  await page.route("**/api/v1/roles/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname.replace(/^\/api\/v1/, "");
    if (request.method() === "GET" && path === "/roles/options/") {
      await route.fulfill({ json: paginated([role]) });
    } else if (request.method() === "GET" && path === "/roles/3/") {
      await route.fulfill({ json: { ...role, permissions: [], permissions_detail: [], capabilities: [], pack_code: "" } });
    } else if (request.method() === "GET" && path === "/roles/capabilities/") {
      await route.fulfill({ json: [{ code: "credit_analyst", label: "Analyste crédit", permission: "credits.view_creditapplication" }] });
    } else if (request.method() === "POST" && path === "/roles/") {
      savePayloads.push(request.postDataJSON() as Record<string, unknown>);
      await route.fulfill({ json: { id: 4, name: "Superviseur recette" } });
    } else if (request.method() === "PATCH" && path === "/roles/3/") {
      const body = request.postDataJSON() as Record<string, unknown>;
      savePayloads.push(body);
      await route.fulfill({ json: { ...role, ...body } });
    } else {
      await route.fallback();
    }
  });
  await page.route("**/api/v1/permissions/", async (route) => {
    await route.fulfill({
      json: [{ id: 11, name: "Consulter les clients", codename: "view_client", app_label: "clients", model: "client", label: "Consultation clients" }],
    });
  });

  await openPage(page, "/admin/roles");
  await expect(page.getByRole("heading", { name: "Rôles & droits" })).toBeVisible();
  await page.getByPlaceholder("Nom du nouveau rôle (ex. Directeur des risques)").fill("Superviseur recette");
  const createRequest = page.waitForRequest((request) => request.url().endsWith("/api/v1/roles/") && request.method() === "POST");
  await page.getByRole("button", { name: "Créer le rôle" }).click();
  await createRequest;
  expect(savePayloads[0]).toEqual({ name: "Superviseur recette" });

  await page.getByRole("button", { name: "Droits" }).click();
  await expect(page.getByText("Analyste crédit")).toBeVisible();
  await page.getByLabel("Analyste crédit").check();
  await page.getByLabel("Consulter les clients").check();
  const updateRequest = page.waitForRequest((request) => request.url().endsWith("/api/v1/roles/3/") && request.method() === "PATCH");
  await page.getByRole("button", { name: "Enregistrer (1)" }).click();
  await updateRequest;
  expect(savePayloads[1]).toMatchObject({ name: "Analyste recette", permissions: [11], capabilities: ["credit_analyst"] });
});

test("le catalogue produits filtre et enregistre les bornes et la tarification", async ({ page }) => {
  const user = makeUser([
    "catalog.view_creditproduct", "catalog.change_creditproduct",
    "catalog.add_creditproduct", "catalog.view_productcategory",
  ]);
  await installApiMocks(page, { user });
  await page.addInitScript((id) => {
    localStorage.setItem("finflow_access", "e2e-access");
    localStorage.setItem("finflow_refresh", "e2e-refresh");
    localStorage.setItem("finflow_tenant", id);
  }, tenantId);

  const category = { id: "category-e2e", code: "MICRO", label: "Microcrédit", description: "", is_active: true };
  const product = {
    id: "product-catalog-e2e", code: "ANC-PROD", label: "Ancien produit", category: category.id,
    category_label: category.label, client_type: "ALL", currency: "XOF", amount_min: "100000",
    amount_max: "50000000", duration_min_months: 3, duration_max_months: 36,
    interest_rate: "12.5", processing_fee_rate: "0", requires_guarantee: false, is_active: true,
  };
  const productQueries: URL[] = [];
  let createPayload: Record<string, unknown> | null = null;
  await page.route(/\/api\/v1\/product-categories\//, async (route) => {
    await route.fulfill({ json: paginated([category]) });
  });
  await page.route(/\/api\/v1\/credit-products\//, async (route) => {
    const request = route.request();
    if (request.method() === "POST") {
      createPayload = request.postDataJSON() as Record<string, unknown>;
      await route.fulfill({ json: { id: "new-product-e2e", ...createPayload } });
      return;
    }
    productQueries.push(new URL(request.url()));
    await route.fulfill({ json: paginated([product]) });
  });

  await openPage(page, "/admin/produits");
  await expect(page.getByRole("heading", { name: "Produits de crédit" })).toBeVisible();
  await expect(page.getByText("Ancien produit")).toBeVisible();
  const filteredRequest = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return url.pathname.endsWith("/credit-products/") && url.searchParams.get("search") === "nouveau-filtre";
  });
  await page.getByPlaceholder("Code, libellé…").fill("nouveau-filtre");
  await filteredRequest;
  expect(productQueries.some((url) => url.searchParams.get("search") === "nouveau-filtre")).toBe(true);

  await page.getByRole("button", { name: "Nouveau produit" }).click();
  await page.getByLabel("Code *").fill("PROD-E2E");
  await page.getByLabel("Libellé *").fill("Produit recette");
  await page.getByLabel("Famille *").selectOption(category.id);
  await page.getByLabel("Montant min").fill("250000");
  await page.getByLabel("Montant max").fill("1500000");
  await page.getByLabel("Durée min (mois)").fill("6");
  await page.getByLabel("Durée max (mois)").fill("24");
  await page.getByLabel("Taux annuel (%)").fill("11.75");
  await page.getByLabel("Frais de dossier (%)").fill("1.25");
  await page.getByLabel("Garantie ou caution obligatoire").check();
  const createRequest = page.waitForRequest((request) => request.url().endsWith("/api/v1/credit-products/") && request.method() === "POST");
  await page.getByRole("button", { name: "Créer le produit" }).click();
  await createRequest;

  expect(createPayload).toMatchObject({
    code: "PROD-E2E", label: "Produit recette", category: category.id, client_type: "ALL",
    currency: "XOF", amount_min: "250000", amount_max: "1500000", duration_min_months: 6,
    duration_max_months: 24, interest_rate: "11.75", processing_fee_rate: "1.25",
    requires_guarantee: true, cbs_credit_product: null,
  });
});

test("un circuit d'approbation se crée inactif avec ses critères", async ({ page }) => {
  const user = makeUser([
    "workflow.view_workflowdefinition", "workflow.add_workflowdefinition", "workflow.change_workflowdefinition",
  ]);
  await installApiMocks(page, { user });
  await page.addInitScript((id) => {
    localStorage.setItem("finflow_access", "e2e-access");
    localStorage.setItem("finflow_refresh", "e2e-refresh");
    localStorage.setItem("finflow_tenant", id);
  }, tenantId);

  let createPayload: Record<string, unknown> | null = null;
  await page.route("**/api/v1/workflow-definitions/", async (route) => {
    const request = route.request();
    if (request.method() === "POST") {
      createPayload = request.postDataJSON() as Record<string, unknown>;
      await route.fulfill({ json: { id: "workflow-new-e2e", ...createPayload } });
      return;
    }
    await route.fulfill({ json: paginated([]) });
  });

  await openPage(page, "/admin/circuits");
  await expect(page.getByRole("heading", { name: "Circuits d'approbation" })).toBeVisible();
  const code = page.getByLabel("Code");
  const name = page.getByLabel("Nom");
  await expect(code).toHaveJSProperty("required", true);
  await expect(name).toHaveJSProperty("required", true);
  await page.getByLabel("Montant min (optionnel)").fill("0");
  await page.getByLabel("Montant max (optionnel)").fill("1000000");
  await code.fill("CIRCUIT-E2E");
  await name.fill("Circuit test recette");
  const createRequest = page.waitForRequest((request) => request.url().endsWith("/api/v1/workflow-definitions/") && request.method() === "POST");
  await page.getByRole("button", { name: "Créer le circuit inactif" }).click();
  await createRequest;

  expect(createPayload).toMatchObject({
    is_active: false, target_type: "CREDIT", code: "CIRCUIT-E2E", name: "Circuit test recette",
    min_amount: "0", max_amount: "1000000", product: null, product_category: null,
  });
});

test("les écrans d'administration filiale imposent une filiale avant de charger les listes", async ({ page }) => {
  const user = makeUser([
    "accounts.view_user", "accounts.change_user", "accounts.view_tenantrole",
    "tenants.view_agency", "tenants.change_agency", "catalog.view_creditproduct",
    "catalog.change_creditproduct", "workflow.view_workflowdefinition",
    "accounts.view_delegation", "accounts.add_delegation", "accounts.change_delegation",
    "catalog.view_rejectreason", "catalog.view_checklistitem", "credits.view_analysisthreshold",
    "documents.view_documentcategory", "contracts.view_contracttemplate",
    "contracts.add_contracttemplate", "contracts.change_contracttemplate",
    "notifications.view_tenantnotificationsettings", "notifications.change_tenantnotificationsettings",
    "credits.view_creditinstructionpolicy", "credits.change_creditinstructionpolicy",
    "collections.view_legalparty", "collections.add_legalparty", "collections.change_legalparty",
    "collections.view_collectiontranche", "collections.view_collectionescalationrule",
  ]);
  user.tenant = null;
  user.is_group_level = true;
  user.is_staff = true;
  const api = await installApiMocks(page, { user });
  await page.addInitScript(() => {
    localStorage.setItem("finflow_access", "e2e-access");
    localStorage.setItem("finflow_refresh", "e2e-refresh");
    localStorage.removeItem("finflow_tenant");
  });

  const screens = [
    ["/admin/utilisateurs", "Utilisateurs"],
    ["/admin/roles", "Rôles & droits"],
    ["/admin/agences", "Agences"],
    ["/admin/produits", "Produits de crédit"],
    ["/admin/circuits", "Circuits d'approbation"],
    ["/admin/delegations", "Délégations"],
    ["/admin/referentiels-metier", "Référentiels métier"],
    ["/admin/contrats", "Modèles de contrats"],
    ["/admin/alertes", "Alertes e-mail"],
    ["/admin/politique-credit", "Politique crédit"],
    ["/admin/tranches-recouvrement", "Tranches de recouvrement"],
    ["/admin/regles-escalade", "Règles d'escalade"],
    ["/admin/intervenants-juridiques", "Intervenants juridiques"],
  ] as const;
  for (const [path, heading] of screens) {
    await openPage(page, path);
    await expect(page.getByRole("heading", { name: heading })).toBeVisible();
    await expect(page.locator("main")).toContainText(/(propre à une filiale|Sélectionnez une filiale|Choisissez une filiale)/);
  }

  const tenantScopedLists = [
    "/users/", "/roles/options/", "/agencies/", "/service-points/",
    "/credit-products/", "/product-categories/", "/workflow-definitions/",
    "/delegations/", "/reject-reasons/", "/contract-templates/",
    "/notification-settings/current/", "/notification-logs/",
    "/credit-instruction-policy/current/", "/collection-tranches/",
    "/collection-escalation-rules/", "/legal-parties/",
  ];
  expect(api.requests.filter((request) => tenantScopedLists.includes(request.path))).toEqual([]);
});

test("une délégation transmet ses dates, son périmètre et ses intervenants", async ({ page }) => {
  const user = makeUser([
    "accounts.view_delegation", "accounts.add_delegation", "accounts.change_delegation",
  ]);
  await installApiMocks(page, { user });
  await page.addInitScript((id) => {
    localStorage.setItem("finflow_access", "e2e-access");
    localStorage.setItem("finflow_refresh", "e2e-refresh");
    localStorage.setItem("finflow_tenant", id);
  }, tenantId);

  const users = [
    { id: "delegator-e2e", username: "manager-e2e", first_name: "Mariam", last_name: "Manager" },
    { id: "delegate-e2e", username: "agent-e2e", first_name: "Awa", last_name: "Agent" },
  ];
  await page.route(/\/api\/v1\/users\//, async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/v1/users/") {
      await route.fulfill({ json: paginated(users) });
      return;
    }
    await route.fallback();
  });

  let createPayload: Record<string, unknown> | null = null;
  await page.route(/\/api\/v1\/delegations\//, async (route) => {
    if (route.request().method() === "POST" && new URL(route.request().url()).pathname === "/api/v1/delegations/") {
      createPayload = route.request().postDataJSON() as Record<string, unknown>;
      await route.fulfill({ json: { id: "delegation-e2e", ...createPayload } });
      return;
    }
    await route.fulfill({ json: paginated([]) });
  });

  await openPage(page, "/admin/delegations");
  await expect(page.getByRole("heading", { name: "Délégations" })).toBeVisible();
  await page.getByLabel("Délégant *").selectOption("delegator-e2e");
  await page.getByLabel("Délégataire *").selectOption("delegate-e2e");
  await page.getByLabel("Motif").fill("Congé planifié");
  await page.getByLabel("Plafond délégué (vide : sans plafond supplémentaire)").fill("750000");
  await page.getByLabel("Nature d'acte").selectOption("DECISIONAL");

  const createResponse = page.waitForResponse((response) => response.url().endsWith("/api/v1/delegations/") && response.request().method() === "POST");
  await page.getByRole("button", { name: "Créer", exact: true }).click();
  await createResponse;
  expect(createPayload).toMatchObject({
    delegator: "delegator-e2e", delegate: "delegate-e2e", reason: "Congé planifié",
    max_amount: "750000", step_kind: "DECISIONAL", is_active: true,
  });
  expect(createPayload?.start_date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  expect(createPayload?.end_date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
});

test("les motifs de rejet sont requis puis normalisés avant création", async ({ page }) => {
  const user = makeUser([
    "catalog.view_rejectreason", "catalog.add_rejectreason",
    "catalog.view_checklistitem",
    "credits.view_analysisthreshold", "documents.view_documentcategory",
  ]);

  await installApiMocks(page, { user });
  await page.addInitScript((id) => {
    localStorage.setItem("finflow_access", "e2e-access");
    localStorage.setItem("finflow_refresh", "e2e-refresh");
    localStorage.setItem("finflow_tenant", id);
  }, tenantId);

  let createPayload: Record<string, unknown> | null = null;
  await page.route(/\/api\/v1\/reject-reasons\//, async (route) => {
    if (route.request().method() === "POST") {
      createPayload = route.request().postDataJSON() as Record<string, unknown>;
      await route.fulfill({ json: { id: "reject-e2e", ...createPayload } });
      return;
    }
    await route.fulfill({ json: paginated([]) });
  });

  await openPage(page, "/admin/referentiels-metier");
  await expect(page.getByRole("heading", { name: "Référentiels métier" })).toBeVisible();
  await expect(page.getByText("Aucun motif de rejet.")).toBeVisible();
  const code = page.getByLabel("Code *");
  const label = page.getByLabel("Libellé *");
  await expect(code).toHaveJSProperty("required", true);
  await expect(label).toHaveJSProperty("required", true);
  await page.getByLabel("Description").fill("Dossier hors politique");
  await code.fill("  risque_eleve  ");
  await label.fill("  Risque élevé  ");

  const createRequest = page.waitForRequest((request) => request.url().endsWith("/api/v1/reject-reasons/") && request.method() === "POST");
  await page.getByRole("button", { name: "Ajouter", exact: true }).click();
  await createRequest;
  expect(createPayload).toEqual({
    code: "RISQUE_ELEVE", label: "Risque élevé", description: "Dossier hors politique", is_active: true,
  });
});

test("un lecteur des référentiels ne charge que son onglet et ne peut rien modifier", async ({ page }) => {
  const user = makeUser([
    "documents.view_documentcategory", "contracts.view_contracttemplate",
  ]);
  const { requests } = await installApiMocks(page, { user });
  await page.addInitScript((id) => {
    localStorage.setItem("finflow_access", "e2e-access");
    localStorage.setItem("finflow_refresh", "e2e-refresh");
    localStorage.setItem("finflow_tenant", id);
  }, tenantId);

  await page.route(/\/api\/v1\/document-categories\//, async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/document-categories/") && route.request().method() === "GET") {
      await route.fulfill({ json: paginated([{
        id: "ged-readonly", code: "ID", label: "Pièce d'identité",
        description: "", tracks_expiry: true, is_active: true,
      }]) });
    } else {
      await route.fallback();
    }
  });

  await openPage(page, "/admin/referentiels-metier");
  await expect(page.locator(".tabs button")).toHaveCount(1);
  await expect(page.getByRole("button", { name: "Catégories GED" })).toBeVisible();
  await expect(page.getByText("Pièce d'identité")).toBeVisible();
  await expect(page.getByRole("button", { name: "Ajouter", exact: true })).toHaveCount(0);
  await expect(page.locator(".table input[type=checkbox]")).toHaveCount(2);
  await expect(page.locator(".table input[type=checkbox]").nth(0)).toBeDisabled();
  await expect(page.getByRole("button", { name: "Supprimer" })).toHaveCount(0);

  await page.route(/\/api\/v1\/contract-templates\//, async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/variables/")) {
      await route.fulfill({ json: { groups: [], loop_help: "" } });
    } else if (path.endsWith("/contract-templates/")) {
      await route.fulfill({ json: paginated([{
        id: "contract-readonly", name: "Contrat lecture seule", category: "LOAN",
        category_display: "Contrat de prêt", applies_to: "ANY",
        applies_to_display: "Tous les clients", product: null, product_label: "",
        amount_min: null, amount_max: null, is_required: true, is_active: true,
        file: "", description: "", engine: "",
      }]) });
    } else {
      await route.fallback();
    }
  });
  await openPage(page, "/admin/contrats");
  await expect(page.getByText("Contrat lecture seule")).toBeVisible();
  await expect(page.getByRole("button", { name: "Nouveau modèle" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Désactiver" })).toHaveCount(0);
  await expect(page.locator(".table button")).toHaveCount(0);

  expect(requests.some((request) => [
    "/reject-reasons/", "/checklist-items/", "/analysis-thresholds/current/",
  ].includes(request.path))).toBe(false);
  expect(requests.some((request) => request.path === "/credit-products/")).toBe(false);
  expect(requests.filter((request) => request.method !== "GET")).toHaveLength(0);
});

test("un modèle de contrat exige un fichier et transmet ses règles et variables", async ({ page }) => {
  const user = makeUser([
    "contracts.view_contracttemplate", "contracts.add_contracttemplate", "contracts.change_contracttemplate",
  ]);
  await installApiMocks(page, { user });
  await page.addInitScript((id) => {
    localStorage.setItem("finflow_access", "e2e-access");
    localStorage.setItem("finflow_refresh", "e2e-refresh");
    localStorage.setItem("finflow_tenant", id);
  }, tenantId);

  let createBody = "";
  await page.route(/\/api\/v1\/contract-templates\//, async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/api/v1/contract-templates/variables/") {
      await route.fulfill({ json: { groups: [], loop_help: "" } });
    } else if (path === "/api/v1/contract-templates/" && request.method() === "POST") {
      createBody = request.postData() ?? "";
      await route.fulfill({ json: { id: "contract-e2e", name: "Contrat recette" } });
    } else {
      await route.fulfill({ json: paginated([]) });
    }
  });

  await openPage(page, "/admin/contrats");
  await expect(page.getByRole("heading", { name: "Modèles de contrats" })).toBeVisible();
  await page.getByRole("button", { name: "Nouveau modèle" }).click();
  await page.getByLabel("Intitulé *").fill("Contrat recette");
  await page.locator("form.tenant-compose-form").getByRole("combobox").nth(0).selectOption("LOAN");
  await page.getByLabel("S'applique à").selectOption("CORPORATE");
  await page.getByLabel("Montant min").fill("500000");
  await page.getByLabel("Montant max").fill("10000000");
  await page.getByLabel("Obligatoire avant mise en place").check();
  await page.getByRole("button", { name: "Ajouter une variable" }).click();
  await page.getByPlaceholder("clé (ex. temoin_nom)").fill("garant_nom");
  await page.getByPlaceholder("libellé").fill("Nom du garant");

  await page.getByRole("button", { name: "Ajouter le modèle" }).click();
  await expect(page.getByText("Veuillez joindre le modèle (.docx ou .xlsx).", { exact: true })).toBeVisible();
  expect(createBody).toBe("");

  await page.getByLabel("Fichier modèle *").setInputFiles({
    name: "contrat-recette.docx",
    mimeType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    buffer: Buffer.from("fichier de recette"),
  });
  const createRequest = page.waitForRequest((request) => request.url().endsWith("/api/v1/contract-templates/") && request.method() === "POST");
  await page.getByRole("button", { name: "Ajouter le modèle" }).click();
  await createRequest;
  expect(createBody).toContain("name\"\r\n\r\nContrat recette");
  expect(createBody).toContain("category\"\r\n\r\nLOAN");
  expect(createBody).toContain("applies_to\"\r\n\r\nCORPORATE");
  expect(createBody).toContain("amount_min\"\r\n\r\n500000");
  expect(createBody).toContain("amount_max\"\r\n\r\n10000000");
  expect(createBody).toContain("is_required\"\r\n\r\ntrue");
  expect(createBody).toContain("garant_nom");
  expect(createBody).toContain("Nom du garant");
  expect(createBody).toContain("contrat-recette.docx");
});

test("le paramétrage d'alertes synchronise SSL, le port et teste sans envoi réel", async ({ page }) => {
  const user = makeUser([
    "notifications.view_tenantnotificationsettings",
    "notifications.change_tenantnotificationsettings",
  ]);
  await installApiMocks(page, { user });
  await page.addInitScript((id) => {
    localStorage.setItem("finflow_access", "e2e-access");
    localStorage.setItem("finflow_refresh", "e2e-refresh");
    localStorage.setItem("finflow_tenant", id);
  }, tenantId);

  const settings = {
    id: "settings-e2e", enabled: true, notify_on_step: true, notify_on_completion: true,
    notify_on_rejection: true, notify_on_return: true, notify_collection_email: false,
    notify_collection_sms: false, notify_collection_transfer: true, notify_collection_dialogue: true,
    from_email: "", reply_to: "", cc_tenant_email: false, smtp_host: "", smtp_port: 587,
    smtp_use_tls: true, smtp_use_ssl: false, smtp_username: "", smtp_password: "",
    smtp_password_configured: false, smtp_configured: false, effective_from_email: "",
    updated_at: "",
  };
  let savePayload: Record<string, unknown> | null = null;
  let testMailCount = 0;
  await page.route(/\/api\/v1\/notification-settings\/current\//, async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path.endsWith("/test/") && request.method() === "POST") {
      testMailCount += 1;
      await route.fulfill({ json: { detail: "Message de test simulé.", from_email: "recette@example.test" } });
    } else if (request.method() === "PATCH") {
      savePayload = request.postDataJSON() as Record<string, unknown>;
      await route.fulfill({ json: { ...settings, ...savePayload } });
    } else {
      await route.fulfill({ json: settings });
    }
  });

  await openPage(page, "/admin/alertes");
  await expect(page.getByRole("heading", { name: "Alertes e-mail" })).toBeVisible();
  await page.getByLabel("Serveur SMTP").fill("smtp.recette.test");
  await page.getByLabel("SSL (port 465)").check();
  await expect(page.getByRole("spinbutton", { name: "Port" })).toHaveValue("465");
  await expect(page.getByLabel("TLS / STARTTLS (port 587)")).not.toBeChecked();
  const saveRequest = page.waitForRequest((request) => request.url().endsWith("/api/v1/notification-settings/current/") && request.method() === "PATCH");
  await page.getByRole("button", { name: "Enregistrer" }).click();
  await saveRequest;
  expect(savePayload).toMatchObject({ smtp_host: "smtp.recette.test", smtp_port: 465, smtp_use_ssl: true, smtp_use_tls: false });
  expect(savePayload).not.toHaveProperty("smtp_password");

  await page.getByRole("button", { name: "Envoyer un test" }).click();
  await expect(page.getByText("Message de test simulé.")).toBeVisible();
  expect(testMailCount).toBe(1);
});

test("checklists et catégories GED transmettent leurs propriétés", async ({ page }) => {
  const user = makeUser([
    "catalog.view_rejectreason", "catalog.view_checklistitem",
    "credits.view_analysisthreshold", "documents.view_documentcategory",
    "catalog.add_checklistitem", "catalog.view_creditproduct",
    "documents.add_documentcategory",
  ]);
  await installApiMocks(page, { user });
  await page.addInitScript((id) => {
    localStorage.setItem("finflow_access", "e2e-access");
    localStorage.setItem("finflow_refresh", "e2e-refresh");
    localStorage.setItem("finflow_tenant", id);
  }, tenantId);

  let checklistPayload: Record<string, unknown> | null = null;
  let gedPayload: Record<string, unknown> | null = null;
  await page.route(/\/api\/v1\/checklist-items\//, async (route) => {
    if (route.request().method() === "POST") {
      checklistPayload = route.request().postDataJSON() as Record<string, unknown>;
      await route.fulfill({ json: { id: "checklist-e2e", ...checklistPayload } });
    } else {
      await route.fulfill({ json: paginated([]) });
    }
  });
  await page.route(/\/api\/v1\/document-categories\//, async (route) => {
    if (route.request().method() === "POST") {
      gedPayload = route.request().postDataJSON() as Record<string, unknown>;
      await route.fulfill({ json: { id: "ged-category-e2e", ...gedPayload } });
    } else {
      await route.fulfill({ json: paginated([]) });
    }
  });

  await openPage(page, "/admin/referentiels-metier");
  await page.getByRole("button", { name: "Checklists produits" }).click();
  await expect(page.getByText("Aucune pièce de checklist.")).toBeVisible();
  await page.getByLabel("Produit *").selectOption("product-e2e");
  await page.getByLabel("Libellé de la pièce *").fill("Justificatif de revenu");
  await page.getByLabel("Ordre").fill("2");
  await page.getByLabel("Obligatoire").uncheck();
  const checklistRequest = page.waitForRequest((request) => request.url().endsWith("/api/v1/checklist-items/") && request.method() === "POST");
  await page.getByRole("button", { name: "Ajouter", exact: true }).click();
  await checklistRequest;
  expect(checklistPayload).toEqual({ product: "product-e2e", label: "Justificatif de revenu", is_mandatory: false, order: 2 });

  await page.getByRole("button", { name: "Catégories GED" }).click();
  await expect(page.getByText("Aucune catégorie GED.")).toBeVisible();
  await page.getByLabel("Code *").fill("  ID_NATIONAL ");
  await page.getByLabel("Libellé *").fill("Pièce d'identité");
  await page.getByLabel("Description").fill("Carte ou passeport en cours de validité");
  await page.getByLabel("Suivi d'expiration").check();
  const gedRequest = page.waitForRequest((request) => request.url().endsWith("/api/v1/document-categories/") && request.method() === "POST");
  await page.getByRole("button", { name: "Ajouter", exact: true }).click();
  await gedRequest;
  expect(gedPayload).toEqual({
    code: "ID_NATIONAL", label: "Pièce d'identité", description: "Carte ou passeport en cours de validité",
    tracks_expiry: true, is_active: true,
  });
});

test("les seuils hérités du centre de configuration restent en lecture seule", async ({ page }) => {
  const user = makeUser([
    "catalog.view_rejectreason", "catalog.view_checklistitem",
    "credits.view_analysisthreshold", "documents.view_documentcategory",
  ]);
  await installApiMocks(page, { user });
  await page.addInitScript((id) => {
    localStorage.setItem("finflow_access", "e2e-access");
    localStorage.setItem("finflow_refresh", "e2e-refresh");
    localStorage.setItem("finflow_tenant", id);
  }, tenantId);

  await openPage(page, "/admin/referentiels-metier");
  await page.getByRole("button", { name: "Seuils d'analyse" }).click();
  await expect(page.getByText("Seuils d'analyse financière (filiale)")).toBeVisible();
  await expect(page.getByLabel("DSCR minimum")).toBeDisabled();
  await expect(page.getByRole("button", { name: "Enregistrer les seuils" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Centre de configuration" })).toBeVisible();
});

test("les paramètres de recouvrement restent consultables sans droit d'écriture", async ({ page }) => {
  const user = makeUser([
    "collections.view_collectiontranche",
    "collections.view_collectionescalationrule",
  ]);
  const { requests } = await installApiMocks(page, { user });
  await page.addInitScript((id) => {
    localStorage.setItem("finflow_access", "e2e-access");
    localStorage.setItem("finflow_refresh", "e2e-refresh");
    localStorage.setItem("finflow_tenant", id);
  }, tenantId);

  await openPage(page, "/admin/tranches-recouvrement");
  await expect(page.getByRole("heading", { name: "Tranches de recouvrement" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Ajouter une tranche" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Enregistrer", exact: true })).toHaveCount(0);

  await openPage(page, "/admin/regles-escalade");
  await expect(page.getByRole("heading", { name: "Règles d'escalade" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Ajouter une règle" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Enregistrer", exact: true })).toHaveCount(0);
  expect(requests.some((request) =>
    request.path.startsWith("/collection-tranches/") ||
    request.path.startsWith("/collection-escalation-rules/"),
  )).toBe(true);
  expect(requests.some((request) =>
    (request.path.startsWith("/collection-tranches/") ||
      request.path.startsWith("/collection-escalation-rules/")) &&
    request.method !== "GET",
  )).toBe(false);
});

test("les tranches enregistrent les bornes et le responsable de chaque niveau", async ({ page }) => {
  const user = makeUser([
    "collections.view_collectiontranche", "collections.change_collectiontranche",
  ]);
  await installApiMocks(page, { user });
  await page.addInitScript((id) => {
    localStorage.setItem("finflow_access", "e2e-access");
    localStorage.setItem("finflow_refresh", "e2e-refresh");
    localStorage.setItem("finflow_tenant", id);
  }, tenantId);

  let replacePayload: Record<string, unknown> | null = null;
  await page.route(/\/api\/v1\/collection-tranches\//, async (route) => {
    const request = route.request();
    if (request.method() === "POST" && new URL(request.url()).pathname.endsWith("/replace/")) {
      replacePayload = request.postDataJSON() as Record<string, unknown>;
      const tranche = { id: "tranche-e2e", position: 1, name: "Recouvrement amiable", min_days_overdue: 1, max_days_overdue: null, owner_kind: "COLLECTION", owner_kind_display: "Service recouvrement", days_label: "1+", is_active: true, created_at: "", updated_at: "" };
      await route.fulfill({ json: [tranche] });
    } else {
      await route.fulfill({ json: paginated([]) });
    }
  });

  await openPage(page, "/admin/tranches-recouvrement");
  await expect(page.getByRole("heading", { name: "Tranches de recouvrement" })).toBeVisible();
  await page.getByRole("button", { name: "Ajouter une tranche" }).click();
  const row = page.locator("tbody tr").first();
  await row.getByPlaceholder("Gestionnaire").fill("Recouvrement amiable");
  await row.getByRole("spinbutton").nth(0).fill("1");
  await row.getByRole("combobox").selectOption("COLLECTION");
  const replaceRequest = page.waitForRequest((request) => request.url().endsWith("/api/v1/collection-tranches/replace/") && request.method() === "POST");
  await page.getByRole("button", { name: "Enregistrer", exact: true }).click();
  await replaceRequest;
  expect(replacePayload).toEqual({
    tranches: [{ name: "Recouvrement amiable", min_days_overdue: 1, max_days_overdue: null, owner_kind: "COLLECTION", is_active: true }],
  });
  await expect(page.getByText(/Tranches enregistrées/)).toBeVisible();
});

test("les règles d'escalade enregistrent le seuil, le stade et l'état", async ({ page }) => {
  const user = makeUser([
    "collections.view_collectionescalationrule",
    "collections.add_collectionescalationrule",
  ]);
  await installApiMocks(page, { user });
  await page.addInitScript((id) => {
    localStorage.setItem("finflow_access", "e2e-access");
    localStorage.setItem("finflow_refresh", "e2e-refresh");
    localStorage.setItem("finflow_tenant", id);
  }, tenantId);

  let createPayload: Record<string, unknown> | null = null;
  await page.route(/\/api\/v1\/collection-escalation-rules\//, async (route) => {
    if (route.request().method() === "POST") {
      createPayload = route.request().postDataJSON() as Record<string, unknown>;
      await route.fulfill({ json: { id: "escalation-e2e", target_stage_display: "Contentieux", ...createPayload } });
    } else {
      await route.fulfill({ json: paginated([]) });
    }
  });

  await openPage(page, "/admin/regles-escalade");
  await expect(page.getByRole("heading", { name: "Règles d'escalade" })).toBeVisible();
  await page.getByRole("button", { name: "Ajouter une règle" }).click();
  const row = page.locator("tbody tr").first();
  await row.getByRole("spinbutton").fill("45");
  await row.getByRole("combobox").selectOption("LITIGATION");
  await row.getByPlaceholder("Précontentieux dès 31 j").fill("Contentieux après 45 jours");
  const saveRequest = page.waitForRequest((request) => request.url().endsWith("/api/v1/collection-escalation-rules/") && request.method() === "POST");
  await page.getByRole("button", { name: "Enregistrer", exact: true }).click();
  await saveRequest;
  expect(createPayload).toEqual({ min_days_overdue: 45, target_stage: "LITIGATION", label: "Contentieux après 45 jours", is_active: true });
  await expect(page.getByText(/Règles enregistrées/)).toBeVisible();
});

test("le référentiel juridique crée un intervenant filtrable et l'audit affiche son état vide", async ({ page }) => {
  const user = makeUser([
    "collections.view_legalparty", "collections.add_legalparty", "collections.change_legalparty", "audit.view_auditlog",
  ]);
  await installApiMocks(page, { user });
  await page.addInitScript((id) => {
    localStorage.setItem("finflow_access", "e2e-access");
    localStorage.setItem("finflow_refresh", "e2e-refresh");
    localStorage.setItem("finflow_tenant", id);
  }, tenantId);

  let createPayload: Record<string, unknown> | null = null;
  const legalQueries: URL[] = [];
  await page.route(/\/api\/v1\/legal-parties\//, async (route) => {
    const request = route.request();
    if (request.method() === "POST") {
      createPayload = request.postDataJSON() as Record<string, unknown>;
      await route.fulfill({ json: { id: "legal-party-e2e", ...createPayload } });
    } else {
      legalQueries.push(new URL(request.url()));
      await route.fulfill({ json: paginated([]) });
    }
  });

  await openPage(page, "/admin/intervenants-juridiques");
  await expect(page.getByRole("heading", { name: "Intervenants juridiques" })).toBeVisible();
  await expect(page.getByText("Aucun intervenant pour ce filtre.")).toBeVisible();
  await page.getByRole("button", { name: "Nouvel intervenant" }).click();
  const form = page.locator("form.tenant-compose-form");
  await form.getByRole("combobox").selectOption("LAWYER");
  await form.getByLabel("Nom / raison sociale *").fill("  Cabinet Test  ");
  await form.getByLabel("N° barreau / agrément").fill("BAR-123");
  await form.getByLabel("Contact").fill("Awa Koné");
  await form.getByLabel("Téléphone").fill("+22501020304");
  await form.getByLabel("E-mail").fill("cabinet@example.test");
  const createRequest = page.waitForRequest((request) => request.url().endsWith("/api/v1/legal-parties/") && request.method() === "POST");
  await page.getByRole("button", { name: "Enregistrer", exact: true }).click();
  await createRequest;
  expect(createPayload).toMatchObject({
    party_type: "LAWYER", name: "Cabinet Test", registration_no: "BAR-123",
    contact_name: "Awa Koné", phone: "+22501020304", email: "cabinet@example.test", is_active: true,
  });

  const filteredRequest = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return url.pathname.endsWith("/legal-parties/") && url.searchParams.get("search") === "Cabinet Test";
  });
  await page.getByPlaceholder("Nom, contact, barreau, téléphone…").fill("Cabinet Test");
  await filteredRequest;
  expect(legalQueries.some((url) => url.searchParams.get("search") === "Cabinet Test")).toBe(true);

  await openPage(page, "/admin/audit");
  await expect(page.getByRole("heading", { name: "Piste d'audit" })).toBeVisible();
  await expect(page.getByText("Aucune opération journalisée.")).toBeVisible();
});

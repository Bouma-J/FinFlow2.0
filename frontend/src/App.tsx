import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import {
  PERM_ADMIN_AGENCIES,
  PERM_ADMIN_ALERTS,
  PERM_ADMIN_AUDIT,
  PERM_ADMIN_CBS_REF,
  PERM_ADMIN_CIRCUITS,
  PERM_ADMIN_CONNECTORS,
  PERM_ADMIN_CONTRACTS,
  PERM_ADMIN_DELEGATIONS,
  PERM_ADMIN_POLICY,
  PERM_ADMIN_CONFIGURATION,
  PERM_ADMIN_COLLECTION_ESCALATION_RULES,
  PERM_ADMIN_COLLECTION_TRANCHES,
  PERM_ADMIN_PRODUCTS,
  PERM_ADMIN_REFERENTIALS,
  PERM_ADMIN_ROLES,
  PERM_ADMIN_USERS,
  PERM_AFTER_SALES,
  PERM_CLIENTS,
  PERM_CLIENTS_CHANGE,
  PERM_COLLECTIONS,
  PERM_CREDIT_CREATE,
  PERM_CREDITS,
  PERM_CREDITS_CHANGE,
  PERM_DASHBOARD,
  PERM_DATIONS,
  PERM_DOCUMENTS,
  PERM_FORMALIZATIONS,
  PERM_GUARANTEES,
  PERM_GUARANTEES_ADD,
  PERM_GUARANTEES_CHANGE,
  PERM_LEGAL_PARTIES,
  PERM_LITIGATION,
  PERM_PRODUCTS,
  PERM_RELEASES,
  PERM_SIMULATOR,
  PERM_SURETIES,
  PERM_TASKS,
  homePath,
} from "@/auth/routePerms";
import { useAuth } from "@/auth/AuthContext";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { AdminRoute } from "@/components/AdminRoute";
import { PermissionRoute } from "@/components/PermissionRoute";
import { Layout } from "@/components/Layout";
import { PageLoading } from "@/components/PageLoading";

const AuditPage = lazy(() => import("@/pages/AuditPage").then((module) => ({ default: module.AuditPage })));
const ClientDetailPage = lazy(() => import("@/pages/ClientDetailPage").then((module) => ({ default: module.ClientDetailPage })));
const ClientEditPage = lazy(() => import("@/pages/ClientEditPage").then((module) => ({ default: module.ClientEditPage })));
const ClientsPage = lazy(() => import("@/pages/ClientsPage").then((module) => ({ default: module.ClientsPage })));
const CreditApplicationDetailPage = lazy(() => import("@/pages/CreditApplicationDetailPage").then((module) => ({ default: module.CreditApplicationDetailPage })));
const CreditApplicationEditPage = lazy(() => import("@/pages/CreditApplicationEditPage").then((module) => ({ default: module.CreditApplicationEditPage })));
const FinancialAnalysisPage = lazy(() => import("@/pages/FinancialAnalysisPage").then((module) => ({ default: module.FinancialAnalysisPage })));
const CreditApplicationNewPage = lazy(() => import("@/pages/CreditApplicationNewPage").then((module) => ({ default: module.CreditApplicationNewPage })));
const CreditApplicationsPage = lazy(() => import("@/pages/CreditApplicationsPage").then((module) => ({ default: module.CreditApplicationsPage })));
const DashboardPage = lazy(() => import("@/pages/DashboardPage").then((module) => ({ default: module.DashboardPage })));
const DocumentsPage = lazy(() => import("@/pages/DocumentsPage").then((module) => ({ default: module.DocumentsPage })));
const GroupConsolidationPage = lazy(() => import("@/pages/GroupConsolidationPage").then((module) => ({ default: module.GroupConsolidationPage })));
const GuaranteeAddPage = lazy(() => import("@/pages/GuaranteeAddPage").then((module) => ({ default: module.GuaranteeAddPage })));
const LoansPage = lazy(() => import("@/pages/LoansPage").then((module) => ({ default: module.LoansPage })));
const GuaranteeDetailPage = lazy(() => import("@/pages/GuaranteeDetailPage").then((module) => ({ default: module.GuaranteeDetailPage })));
const GuaranteeEditPage = lazy(() => import("@/pages/GuaranteeEditPage").then((module) => ({ default: module.GuaranteeEditPage })));
const GuaranteesPage = lazy(() => import("@/pages/GuaranteesPage").then((module) => ({ default: module.GuaranteesPage })));
const GuaranteeReleaseDetailPage = lazy(() => import("@/pages/GuaranteeReleasesPage").then((module) => ({ default: module.GuaranteeReleaseDetailPage })));
const GuaranteeReleaseNewPage = lazy(() => import("@/pages/GuaranteeReleasesPage").then((module) => ({ default: module.GuaranteeReleaseNewPage })));
const GuaranteeReleasesPage = lazy(() => import("@/pages/GuaranteeReleasesPage").then((module) => ({ default: module.GuaranteeReleasesPage })));
const DationDetailPage = lazy(() => import("@/pages/DationsPage").then((module) => ({ default: module.DationDetailPage })));
const DationNewPage = lazy(() => import("@/pages/DationsPage").then((module) => ({ default: module.DationNewPage })));
const DationsPage = lazy(() => import("@/pages/DationsPage").then((module) => ({ default: module.DationsPage })));
const FormalizationDetailPage = lazy(() => import("@/pages/FormalizationsPage").then((module) => ({ default: module.FormalizationDetailPage })));
const FormalizationNewPage = lazy(() => import("@/pages/FormalizationsPage").then((module) => ({ default: module.FormalizationNewPage })));
const FormalizationsPage = lazy(() => import("@/pages/FormalizationsPage").then((module) => ({ default: module.FormalizationsPage })));
const CollectionsPage = lazy(() => import("@/pages/CollectionsPage").then((module) => ({ default: module.CollectionsPage })));
const AfterSalesHubPage = lazy(() => import("@/pages/AfterSalesHubPage").then((module) => ({ default: module.AfterSalesHubPage })));
const CollectionCaseDetailPage = lazy(() => import("@/pages/CollectionCaseDetailPage").then((module) => ({ default: module.CollectionCaseDetailPage })));
const LegalPartiesPage = lazy(() => import("@/pages/admin/LegalPartiesPage").then((module) => ({ default: module.LegalPartiesPage })));
const LitigationDetailPage = lazy(() => import("@/pages/LitigationDetailPage").then((module) => ({ default: module.LitigationDetailPage })));
const SuretyEngagementAddPage = lazy(() => import("@/pages/SuretyEngagementAddPage").then((module) => ({ default: module.SuretyEngagementAddPage })));
const LoginPage = lazy(() => import("@/pages/LoginPage").then((module) => ({ default: module.LoginPage })));
const ForceChangePasswordPage = lazy(() => import("@/pages/ForceChangePasswordPage").then((module) => ({ default: module.ForceChangePasswordPage })));
const ProfilePage = lazy(() => import("@/pages/ProfilePage").then((module) => ({ default: module.ProfilePage })));
const ProductsPage = lazy(() => import("@/pages/ProductsPage").then((module) => ({ default: module.ProductsPage })));
const SimulatorPage = lazy(() => import("@/pages/SimulatorPage").then((module) => ({ default: module.SimulatorPage })));
const SuretiesPage = lazy(() => import("@/pages/SuretiesPage").then((module) => ({ default: module.SuretiesPage })));
const SuretyDetailPage = lazy(() => import("@/pages/SuretyDetailPage").then((module) => ({ default: module.SuretyDetailPage })));
const SuretyEditPage = lazy(() => import("@/pages/SuretyEditPage").then((module) => ({ default: module.SuretyEditPage })));
const TasksPage = lazy(() => import("@/pages/TasksPage").then((module) => ({ default: module.TasksPage })));
const AdminAgenciesPage = lazy(() => import("@/pages/admin/AgenciesPage").then((module) => ({ default: module.AdminAgenciesPage })));
const AdminTenantsPage = lazy(() => import("@/pages/admin/TenantsPage").then((module) => ({ default: module.AdminTenantsPage })));
const AdminBusinessReferentialsPage = lazy(() => import("@/pages/admin/BusinessReferentialsPage").then((module) => ({ default: module.AdminBusinessReferentialsPage })));
const AdminConnectorsPage = lazy(() => import("@/pages/admin/ConnectorsPage").then((module) => ({ default: module.AdminConnectorsPage })));
const AdminContractsPage = lazy(() => import("@/pages/admin/ContractsAdminPage").then((module) => ({ default: module.AdminContractsPage })));
const AdminNotificationsPage = lazy(() => import("@/pages/admin/NotificationsPage").then((module) => ({ default: module.AdminNotificationsPage })));
const AdminCollectionEscalationRulesPage = lazy(() => import("@/pages/admin/CollectionEscalationRulesPage").then((module) => ({ default: module.AdminCollectionEscalationRulesPage })));
const AdminCollectionTranchesPage = lazy(() => import("@/pages/admin/CollectionTranchesPage").then((module) => ({ default: module.AdminCollectionTranchesPage })));
const AdminCreditPolicyPage = lazy(() => import("@/pages/admin/CreditPolicyPage").then((module) => ({ default: module.AdminCreditPolicyPage })));
const AdminConfigurationPage = lazy(() => import("@/pages/admin/ConfigurationPage").then((module) => ({ default: module.AdminConfigurationPage })));
const AdminDelegationsPage = lazy(() => import("@/pages/admin/DelegationsPage").then((module) => ({ default: module.AdminDelegationsPage })));
const AdminProductsPage = lazy(() => import("@/pages/admin/ProductsAdminPage").then((module) => ({ default: module.AdminProductsPage })));
const AdminCbsReferentialsPage = lazy(() => import("@/pages/admin/CbsReferentialsPage").then((module) => ({ default: module.AdminCbsReferentialsPage })));
const AdminCbsSituationProbePage = lazy(() => import("@/pages/admin/CbsSituationProbePage").then((module) => ({ default: module.AdminCbsSituationProbePage })));
const AdminRolesPage = lazy(() => import("@/pages/admin/RolesPage").then((module) => ({ default: module.AdminRolesPage })));
const AdminUsersPage = lazy(() => import("@/pages/admin/UsersPage").then((module) => ({ default: module.AdminUsersPage })));
const AdminWorkflowPage = lazy(() => import("@/pages/admin/WorkflowPage").then((module) => ({ default: module.AdminWorkflowPage })));

function FallbackHome() {
  const { user } = useAuth();
  return <Navigate to={homePath(user)} replace />;
}

export default function App() {
  return (
    <Routes>
      <Route
        path="/login"
        element={
          <Suspense fallback={<PageLoading />}>
            <LoginPage />
          </Suspense>
        }
      />
      <Route
        path="/login/:tenantCode"
        element={
          <Suspense fallback={<PageLoading />}>
            <LoginPage />
          </Suspense>
        }
      />
      <Route
        path="/changer-mot-de-passe"
        element={
          <ProtectedRoute>
            <Suspense fallback={<PageLoading />}>
              <ForceChangePasswordPage />
            </Suspense>
          </ProtectedRoute>
        }
      />
      <Route
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route
          path="/"
          element={
            <PermissionRoute anyOf={PERM_DASHBOARD}>
              <DashboardPage />
            </PermissionRoute>
          }
        />
        <Route path="/profil" element={<ProfilePage />} />
        <Route
          path="/clients"
          element={
            <PermissionRoute anyOf={PERM_CLIENTS}>
              <ClientsPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/clients/:id"
          element={
            <PermissionRoute anyOf={PERM_CLIENTS}>
              <ClientDetailPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/clients/:id/modifier"
          element={
            <PermissionRoute anyOf={PERM_CLIENTS_CHANGE}>
              <ClientEditPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/dossiers"
          element={
            <PermissionRoute anyOf={PERM_CREDITS}>
              <CreditApplicationsPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/prets"
          element={
            <PermissionRoute anyOf={PERM_CREDITS}>
              <LoansPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/dossiers/nouveau"
          element={
            <PermissionRoute anyOf={PERM_CREDIT_CREATE}>
              <CreditApplicationNewPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/dossiers/:id"
          element={
            <PermissionRoute anyOf={PERM_CREDITS}>
              <CreditApplicationDetailPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/dossiers/:id/modifier"
          element={
            <PermissionRoute anyOf={PERM_CREDITS_CHANGE}>
              <CreditApplicationEditPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/dossiers/:id/analyse-financiere"
          element={
            <PermissionRoute anyOf={PERM_CREDITS}>
              <FinancialAnalysisPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/dossiers/:id/analyse-financiere/:analysisId"
          element={
            <PermissionRoute anyOf={PERM_CREDITS}>
              <FinancialAnalysisPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/dossiers/:id/garanties/nouvelle"
          element={
            <PermissionRoute anyOf={PERM_GUARANTEES_ADD}>
              <GuaranteeAddPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/dossiers/:appId/garanties/:id"
          element={
            <PermissionRoute anyOf={PERM_GUARANTEES}>
              <GuaranteeDetailPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/dossiers/:appId/cautions/:id"
          element={
            <PermissionRoute anyOf={PERM_SURETIES}>
              <SuretyDetailPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/dossiers/:id/cautions/nouvelle"
          element={
            <PermissionRoute anyOf={PERM_SURETIES}>
              <SuretyEngagementAddPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/taches"
          element={
            <PermissionRoute anyOf={PERM_TASKS}>
              <TasksPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/produits"
          element={
            <PermissionRoute anyOf={PERM_PRODUCTS}>
              <ProductsPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/cautions"
          element={
            <PermissionRoute anyOf={PERM_SURETIES}>
              <SuretiesPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/cautions/:id"
          element={
            <PermissionRoute anyOf={PERM_SURETIES}>
              <SuretyDetailPage manageable />
            </PermissionRoute>
          }
        />
        <Route
          path="/cautions/:id/modifier"
          element={
            <PermissionRoute anyOf={PERM_SURETIES}>
              <SuretyEditPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/garanties"
          element={
            <PermissionRoute anyOf={PERM_GUARANTEES}>
              <GuaranteesPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/garanties/:id"
          element={
            <PermissionRoute anyOf={PERM_GUARANTEES}>
              <GuaranteeDetailPage manageable />
            </PermissionRoute>
          }
        />
        <Route
          path="/garanties/:id/modifier"
          element={
            <PermissionRoute anyOf={PERM_GUARANTEES_CHANGE}>
              <GuaranteeEditPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/apres-vente"
          element={
            <PermissionRoute anyOf={PERM_AFTER_SALES}>
              <AfterSalesHubPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/mains-levees"
          element={
            <PermissionRoute anyOf={PERM_RELEASES}>
              <GuaranteeReleasesPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/mains-levees/nouvelle"
          element={
            <PermissionRoute
              anyOf={["guarantees.initiate_guaranteereleaserequest"]}
            >
              <GuaranteeReleaseNewPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/mains-levees/:id"
          element={
            <PermissionRoute anyOf={PERM_RELEASES}>
              <GuaranteeReleaseDetailPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/dations"
          element={
            <PermissionRoute anyOf={PERM_DATIONS}>
              <DationsPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/dations/nouvelle"
          element={
            <PermissionRoute anyOf={["guarantees.initiate_dationrequest"]}>
              <DationNewPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/dations/:id"
          element={
            <PermissionRoute anyOf={PERM_DATIONS}>
              <DationDetailPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/formalisations"
          element={
            <PermissionRoute anyOf={PERM_FORMALIZATIONS}>
              <FormalizationsPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/formalisations/nouvelle"
          element={
            <PermissionRoute
              anyOf={["guarantees.initiate_guaranteeformalizationrequest"]}
            >
              <FormalizationNewPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/formalisations/:id"
          element={
            <PermissionRoute anyOf={PERM_FORMALIZATIONS}>
              <FormalizationDetailPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/documents"
          element={
            <PermissionRoute anyOf={PERM_DOCUMENTS}>
              <DocumentsPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/recouvrement"
          element={
            <PermissionRoute anyOf={PERM_COLLECTIONS}>
              <CollectionsPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/recouvrement/:id"
          element={
            <PermissionRoute anyOf={PERM_COLLECTIONS}>
              <CollectionCaseDetailPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/recouvrement/:caseId/contentieux/:litId"
          element={
            <PermissionRoute anyOf={PERM_LITIGATION}>
              <LitigationDetailPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/intervenants-juridiques"
          element={<Navigate to="/admin/intervenants-juridiques" replace />}
        />
        <Route
          path="/simulateur"
          element={
            <PermissionRoute anyOf={PERM_SIMULATOR}>
              <SimulatorPage />
            </PermissionRoute>
          }
        />
        <Route path="/audit" element={<Navigate to="/admin/audit" replace />} />
        <Route
          path="/admin/filiales"
          element={
            <AdminRoute>
              <AdminTenantsPage />
            </AdminRoute>
          }
        />
        <Route
          path="/admin/consolidation"
          element={
            <AdminRoute>
              <PermissionRoute anyOf={PERM_DASHBOARD}>
                <GroupConsolidationPage />
              </PermissionRoute>
            </AdminRoute>
          }
        />
        <Route
          path="/admin/agences"
          element={
            <AdminRoute>
              <PermissionRoute anyOf={PERM_ADMIN_AGENCIES}>
                <AdminAgenciesPage />
              </PermissionRoute>
            </AdminRoute>
          }
        />
        <Route
          path="/admin/utilisateurs"
          element={
            <AdminRoute>
              <PermissionRoute anyOf={PERM_ADMIN_USERS}>
                <AdminUsersPage />
              </PermissionRoute>
            </AdminRoute>
          }
        />
        <Route
          path="/admin/roles"
          element={
            <PermissionRoute anyOf={PERM_ADMIN_ROLES}>
              <AdminRolesPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/admin/produits"
          element={
            <AdminRoute>
              <PermissionRoute anyOf={PERM_ADMIN_PRODUCTS}>
                <AdminProductsPage />
              </PermissionRoute>
            </AdminRoute>
          }
        />
        <Route
          path="/admin/referentiels-cbs"
          element={
            <AdminRoute>
              <PermissionRoute anyOf={PERM_ADMIN_CBS_REF}>
                <AdminCbsReferentialsPage />
              </PermissionRoute>
            </AdminRoute>
          }
        />
        <Route
          path="/admin/referentiels-metier"
          element={
            <AdminRoute>
              <PermissionRoute anyOf={PERM_ADMIN_REFERENTIALS}>
                <AdminBusinessReferentialsPage />
              </PermissionRoute>
            </AdminRoute>
          }
        />
        <Route
          path="/admin/intervenants-juridiques"
          element={
            <PermissionRoute anyOf={PERM_LEGAL_PARTIES}>
              <LegalPartiesPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/admin/circuits"
          element={
            <AdminRoute>
              <PermissionRoute anyOf={PERM_ADMIN_CIRCUITS}>
                <AdminWorkflowPage />
              </PermissionRoute>
            </AdminRoute>
          }
        />
        <Route
          path="/admin/delegations"
          element={
            <AdminRoute>
              <PermissionRoute anyOf={PERM_ADMIN_DELEGATIONS}>
                <AdminDelegationsPage />
              </PermissionRoute>
            </AdminRoute>
          }
        />
        <Route
          path="/admin/contrats"
          element={
            <AdminRoute>
              <PermissionRoute anyOf={PERM_ADMIN_CONTRACTS}>
                <AdminContractsPage />
              </PermissionRoute>
            </AdminRoute>
          }
        />
        <Route
          path="/admin/connecteurs"
          element={
            <AdminRoute>
              <PermissionRoute anyOf={PERM_ADMIN_CONNECTORS}>
                <AdminConnectorsPage />
              </PermissionRoute>
            </AdminRoute>
          }
        />
        <Route
          path="/admin/verification-situation"
          element={
            <AdminRoute>
              <AdminCbsSituationProbePage />
            </AdminRoute>
          }
        />
        <Route
          path="/admin/alertes"
          element={
            <PermissionRoute anyOf={PERM_ADMIN_ALERTS}>
              <AdminNotificationsPage />
            </PermissionRoute>
          }
        />
        <Route
          path="/admin/politique-credit"
          element={
            <AdminRoute>
              <PermissionRoute anyOf={PERM_ADMIN_POLICY}>
                <AdminCreditPolicyPage />
              </PermissionRoute>
            </AdminRoute>
          }
        />
        <Route path="/admin/configuration" element={
          <AdminRoute><PermissionRoute anyOf={PERM_ADMIN_CONFIGURATION}><AdminConfigurationPage /></PermissionRoute></AdminRoute>
        } />
        <Route
          path="/admin/tranches-recouvrement"
          element={
            <AdminRoute>
              <PermissionRoute anyOf={PERM_ADMIN_COLLECTION_TRANCHES}>
                <AdminCollectionTranchesPage />
              </PermissionRoute>
            </AdminRoute>
          }
        />
        <Route
          path="/admin/regles-escalade"
          element={
            <AdminRoute>
              <PermissionRoute anyOf={PERM_ADMIN_COLLECTION_ESCALATION_RULES}>
                <AdminCollectionEscalationRulesPage />
              </PermissionRoute>
            </AdminRoute>
          }
        />
        <Route
          path="/admin/audit"
          element={
            <AdminRoute>
              <PermissionRoute anyOf={PERM_ADMIN_AUDIT}>
                <AuditPage />
              </PermissionRoute>
            </AdminRoute>
          }
        />
      </Route>
      <Route path="*" element={<FallbackHome />} />
    </Routes>
  );
}

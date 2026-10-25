import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, LineChart } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api } from "@/api/client";
import type {
  ApprovalTask,
  CreditApplication,
  FinancialAnalysis,
  Paginated,
} from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { hasPerm } from "@/auth/permissions";
import { FinancialAnalysisForm } from "@/components/FinancialAnalysisForm";
import { ErrorState, PageHeader, Spinner } from "@/components/ui";

const OPEN_FOR_CONTRIBUTION = ["DRAFT", "SUBMITTED", "IN_APPROVAL", "RETURNED"];
const ANALYSIS_LOCKED = ["DISBURSED", "CLOSED", "CANCELLED", "REJECTED"];

export function FinancialAnalysisPage() {
  const { id, analysisId } = useParams<{ id: string; analysisId?: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();

  const {
    data: app,
    isLoading: loadingApp,
    isError: errorApp,
    refetch: refetchApp,
  } = useQuery({
    queryKey: ["credit-application", id],
    queryFn: async () =>
      (await api.get<CreditApplication>(`/credit-applications/${id}/`)).data,
    enabled: !!id,
  });

  const {
    data: existing,
    isLoading: loadingAnalysis,
    isError: errorAnalysis,
    refetch: refetchAnalysis,
  } = useQuery({
    queryKey: ["financial-analysis-item", analysisId],
    queryFn: async () =>
      (
        await api.get<FinancialAnalysis>(
          `/financial-analyses/${analysisId}/`,
        )
      ).data,
    enabled: !!analysisId,
  });

  const { data: myTasks, isLoading: loadingTasks } = useQuery({
    queryKey: ["my-pending-tasks"],
    queryFn: async () =>
      (await api.get<Paginated<ApprovalTask>>("/approval-tasks/my_pending/"))
        .data,
    enabled: !!user && !analysisId,
  });

  if (
    loadingApp ||
    (analysisId && loadingAnalysis) ||
    (!analysisId && !!user && loadingTasks)
  ) {
    return <Spinner />;
  }

  if (errorApp || !app) {
    return (
      <div className="page-shell">
        <PageHeader
          icon={LineChart}
          title="Analyse financière"
          subtitle="Chargement impossible"
          actions={
            <Link
              className="btn btn-ghost"
              to={id ? `/dossiers/${id}` : "/dossiers"}
            >
              <ArrowLeft />
              Retour
            </Link>
          }
        />
        <ErrorState
          message="Impossible de charger le dossier."
          onRetry={() => refetchApp()}
        />
      </div>
    );
  }

  if (analysisId && (errorAnalysis || !existing)) {
    return (
      <div className="page-shell">
        <PageHeader
          icon={LineChart}
          title="Analyse financière"
          subtitle="Chargement impossible"
          actions={
            <Link className="btn btn-ghost" to={`/dossiers/${id}`}>
              <ArrowLeft />
              Retour au dossier
            </Link>
          }
        />
        <ErrorState
          message="Impossible de charger l'analyse financière."
          onRetry={() => refetchAnalysis()}
        />
      </div>
    );
  }

  const backTo = `/dossiers/${id}`;
  const isEdit = !!analysisId;
  const uid = user?.id;
  const isSuper = !!user?.is_superuser;
  const canAdd = hasPerm(user, "credits.add_financialanalysis");
  const canChange = hasPerm(user, "credits.change_financialanalysis");
  const isOwner =
    !!uid && (app.created_by === uid || app.submitted_by === uid);
  const myTask =
    myTasks?.results?.find((t) => t.application?.id === app.id) ?? null;
  const openWindow = OPEN_FOR_CONTRIBUTION.includes(app.status);
  const analysisLocked = ANALYSIS_LOCKED.includes(app.status);
  const canContributeWindow =
    !analysisLocked && (isSuper || ((isOwner && openWindow) || !!myTask));

  if (isEdit) {
    const isAuthor = isSuper || (!!uid && existing?.created_by === uid);
    if (
      analysisLocked ||
      !canChange ||
      !isAuthor ||
      !(existing?.can_edit || (isSuper && !analysisLocked))
    ) {
      return (
        <div className="page-shell">
          <PageHeader
            icon={LineChart}
            title="Analyse financière"
            subtitle="Accès refusé"
            actions={
              <Link className="btn btn-ghost" to={backTo}>
                <ArrowLeft />
                Retour au dossier
              </Link>
            }
          />
          <p className="form-error">
            {analysisLocked
              ? "Ce dossier est mis en place ou clôturé : l'analyse financière n'est plus modifiable."
              : "Vous ne pouvez pas modifier cette analyse (droits insuffisants ou fenêtre de contribution fermée)."}
          </p>
        </div>
      );
    }
  } else if (!canAdd || !canContributeWindow) {
    return (
      <div>
        <PageHeader
          icon={LineChart}
          title="Nouvelle analyse financière"
          subtitle="Accès refusé"
          actions={
            <Link className="btn btn-ghost" to={backTo}>
              <ArrowLeft />
              Retour au dossier
            </Link>
          }
        />
        <p className="form-error">
          {analysisLocked
            ? "Ce dossier est mis en place ou clôturé : aucune nouvelle analyse financière ne peut être ajoutée."
            : "Vous n'êtes pas autorisé à ajouter une analyse sur ce dossier."}
        </p>
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        icon={LineChart}
        title={
          isEdit
            ? "Modifier l'analyse financière"
            : "Nouvelle analyse financière"
        }
        subtitle={`${app.client_display} · dossier ${app.reference || app.id.slice(0, 8)}`}
        actions={
          <Link className="btn btn-ghost" to={backTo}>
            <ArrowLeft />
            Retour au dossier
          </Link>
        }
      />

      <FinancialAnalysisForm
        mode={isEdit ? "edit" : "create"}
        analysisId={analysisId}
        initial={isEdit ? existing : undefined}
        application={app}
        backTo={backTo}
        onSaved={() => navigate(backTo)}
      />
    </div>
  );
}

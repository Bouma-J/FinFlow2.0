import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, FilePenLine, TriangleAlert } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api } from "@/api/client";
import type { CreditApplication } from "@/api/types";
import { CreditApplicationForm } from "@/components/CreditApplicationForm";
import { ErrorState, PageHeader, Spinner } from "@/components/ui";

const EDITABLE_STATUSES = ["DRAFT", "RETURNED"];

export function CreditApplicationEditPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const { data: app, isLoading, isError, refetch } = useQuery({
    queryKey: ["credit-application", id],
    queryFn: async () =>
      (await api.get<CreditApplication>(`/credit-applications/${id}/`)).data,
    enabled: !!id,
  });

  if (isLoading) return <Spinner />;
  if (isError || !app)
    return (
      <ErrorState
        message="Impossible de charger le dossier de crédit."
        onRetry={() => refetch()}
      />
    );

  const editable = EDITABLE_STATUSES.includes(app.status);

  return (
    <div className="page-shell">
      <PageHeader
        icon={FilePenLine}
        title={`Modifier le dossier ${app.reference || app.id.slice(0, 8)}`}
        subtitle={`${app.client_display} · ${app.product_label}`}
        actions={
          <Link className="btn btn-ghost" to={`/dossiers/${id}`}>
            <ArrowLeft />
            Retour au dossier
          </Link>
        }
      />

      {!editable ? (
        <div className="notice-warning">
          <TriangleAlert size={18} />
          <span>
            Ce dossier ne peut plus être modifié dans son état actuel («{" "}
            {app.status_display} »). Annulez d'abord la soumission pour le
            repasser en brouillon.
          </span>
        </div>
      ) : (
        <CreditApplicationForm
          initial={app}
          onCreated={() => navigate(`/dossiers/${id}`)}
          onCancel={() => navigate(`/dossiers/${id}`)}
        />
      )}
    </div>
  );
}

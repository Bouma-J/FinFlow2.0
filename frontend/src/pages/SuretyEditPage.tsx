import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, UserRoundPen } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api } from "@/api/client";
import type { Surety } from "@/api/types";
import { SuretyForm } from "@/components/SuretyForm";
import { ErrorState, PageHeader, Spinner } from "@/components/ui";

export function SuretyEditPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const { data: surety, isLoading, isError, refetch } = useQuery({
    queryKey: ["surety", id],
    queryFn: async () => (await api.get<Surety>(`/sureties/${id}/`)).data,
    enabled: !!id,
  });

  if (isLoading) return <Spinner />;
  if (isError || !surety)
    return (
      <ErrorState
        message="Impossible de charger la caution."
        onRetry={() => refetch()}
      />
    );

  return (
    <div className="page-shell">
      <PageHeader
        icon={UserRoundPen}
        title={`Modifier — ${surety.display_name}`}
        subtitle="Caution"
        actions={
          <Link className="btn btn-ghost" to={`/cautions/${surety.id}`}>
            <ArrowLeft />
            Retour
          </Link>
        }
      />
      <SuretyForm
        initial={surety}
        onSuccess={() => navigate(`/cautions/${surety.id}`)}
        onCancel={() => navigate(`/cautions/${surety.id}`)}
      />
    </div>
  );
}

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ShieldCheck } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api } from "@/api/client";
import type { CreditApplication, Guarantee } from "@/api/types";
import { GuaranteeForm } from "@/components/GuaranteeForm";
import { ErrorState, PageHeader, Spinner } from "@/components/ui";

export function GuaranteeEditPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const { data: guarantee, isLoading, isError, refetch } = useQuery({
    queryKey: ["guarantee", id],
    queryFn: async () =>
      (await api.get<Guarantee>(`/guarantees/${id}/`)).data,
    enabled: !!id,
  });

  const { data: app } = useQuery({
    queryKey: ["credit-application", guarantee?.application],
    queryFn: async () =>
      (
        await api.get<CreditApplication>(
          `/credit-applications/${guarantee!.application}/`,
        )
      ).data,
    enabled: !!guarantee?.application,
  });

  if (isLoading) return <Spinner />;
  if (isError || !guarantee)
    return (
      <ErrorState
        message="Impossible de charger la garantie."
        onRetry={() => refetch()}
      />
    );

  const loanAmount = Number(
    app?.amount_approved || app?.amount_proposed || app?.amount_requested || 0,
  );

  return (
    <div className="page-shell">
      <PageHeader
        icon={ShieldCheck}
        title="Modifier la garantie"
        subtitle={guarantee.reference || guarantee.type_display}
        actions={
          <Link className="btn btn-ghost" to={`/garanties/${id}`}>
            <ArrowLeft />
            Retour
          </Link>
        }
      />
      <GuaranteeForm
        mode="edit"
        guaranteeId={guarantee.id}
        initial={guarantee}
        loanAmount={loanAmount}
        backTo={`/garanties/${id}`}
        onSaved={() => navigate(`/garanties/${id}`)}
      />
    </div>
  );
}

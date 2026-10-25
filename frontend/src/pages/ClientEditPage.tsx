import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, UserPen } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api } from "@/api/client";
import type { Client } from "@/api/types";
import { ClientForm } from "@/components/ClientForm";
import { ErrorState, PageHeader, Spinner } from "@/components/ui";

export function ClientEditPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const { data: client, isLoading, isError, refetch } = useQuery({
    queryKey: ["client", id],
    queryFn: async () => (await api.get<Client>(`/clients/${id}/`)).data,
    enabled: !!id,
  });

  if (isLoading) return <Spinner />;
  if (isError || !client)
    return (
      <ErrorState
        message="Impossible de charger le client."
        onRetry={() => refetch()}
      />
    );

  return (
    <div className="page-shell">
      <PageHeader
        icon={UserPen}
        title={`Modifier — ${client.display_name}`}
        subtitle={`Matricule ${client.reference}`}
        actions={
          <Link className="btn btn-ghost" to={`/clients/${client.id}`}>
            <ArrowLeft />
            Retour
          </Link>
        }
      />
      <ClientForm
        initial={client}
        onSuccess={() => navigate(`/clients/${client.id}`)}
        onCancel={() => navigate(`/clients/${client.id}`)}
      />
    </div>
  );
}

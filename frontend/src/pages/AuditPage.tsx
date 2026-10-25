import { useQuery } from "@tanstack/react-query";
import { ScrollText } from "lucide-react";
import { useState } from "react";

import { api } from "@/api/client";
import type { AuditLog, Paginated } from "@/api/types";
import {
  Badge,
  PageHeader,
  PaginationBar,
  QueryStatus,
  formatDate,
} from "@/components/ui";

export function AuditPage() {
  const [page, setPage] = useState(1);
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["audit-logs", page],
    queryFn: async () =>
      (await api.get<Paginated<AuditLog>>("/audit-logs/", { params: { page } }))
        .data,
  });

  return (
    <div className="page-shell">
      <PageHeader
        icon={ScrollText}
        title="Piste d'audit"
        subtitle="Traçabilité des opérations"
      />
      <QueryStatus
        isLoading={isLoading}
        isError={isError}
        isEmpty={!data?.results.length}
        emptyMessage="Aucune opération journalisée."
        onRetry={() => refetch()}
      >
        <>
          <table className="table card">
            <thead>
              <tr>
                <th>Date</th>
                <th>Action</th>
                <th>Entité</th>
                <th>Objet</th>
                <th>Utilisateur</th>
                <th>IP</th>
              </tr>
            </thead>
            <tbody>
              {(data?.results ?? []).map((log) => (
                <tr key={log.id}>
                  <td>{formatDate(log.timestamp)}</td>
                  <td>
                    <Badge value={log.action} />
                  </td>
                  <td className="muted small">{log.model_label}</td>
                  <td>{log.object_repr}</td>
                  <td>{log.user_display || "—"}</td>
                  <td className="muted small">{log.ip_address || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <PaginationBar page={page} count={data?.count ?? 0} onPageChange={setPage} />
        </>
      </QueryStatus>
    </div>
  );
}

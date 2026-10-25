import { CircleAlert, Inbox, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

export function PageHeader({
  title,
  subtitle,
  actions,
  icon: Icon,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  icon?: LucideIcon;
}) {
  return (
    <div className="page-header">
      <div className="page-title-wrap">
        {Icon && (
          <span className="page-title-icon">
            <Icon size={24} />
          </span>
        )}
        <div>
          <h1 className="page-title">{title}</h1>
          {subtitle && <p className="page-subtitle">{subtitle}</p>}
        </div>
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </div>
  );
}

export function StatCard({
  label,
  value,
  hint,
  tone = "default",
  icon: Icon,
  action,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  tone?: "default" | "success" | "warning" | "danger";
  icon?: LucideIcon;
  /** Lien / action discrète à droite du KPI (la carte elle-même n'est pas cliquable). */
  action?: ReactNode;
}) {
  return (
    <div className={`stat-card tone-${tone}${action ? " has-action" : ""}`}>
      {Icon && (
        <span className="stat-icon">
          <Icon size={22} />
        </span>
      )}
      <span className="stat-body">
        <span className="stat-label">{label}</span>
        <span className="stat-value">{value}</span>
        {hint && <span className="stat-hint">{hint}</span>}
      </span>
      {action && <div className="stat-card-action">{action}</div>}
    </div>
  );
}

const STATUS_TONES: Record<string, string> = {
  APPROVED: "success",
  DISBURSED: "success",
  VALIDATED: "success",
  REJECTED: "danger",
  RETURNED: "warning",
  DISBURSEMENT_PENDING: "warning",
  IN_APPROVAL: "info",
  SUBMITTED: "info",
  PENDING: "warning",
  DRAFT: "muted",
  ACTIVE: "success",
};

export function Badge({
  value,
  label,
  tone: toneOverride,
  title,
}: {
  value: string;
  label?: string;
  /** Force la tonalité quand `value` n'est pas un statut métier connu. */
  tone?: "success" | "warning" | "danger" | "info" | "muted";
  title?: string;
}) {
  const tone = toneOverride ?? STATUS_TONES[value] ?? "muted";
  return (
    <span className={`badge badge-${tone}`} title={title}>
      {label ?? value}
    </span>
  );
}

export function Spinner() {
  return <div className="spinner" aria-label="Chargement" />;
}

export function EmptyState({ message }: { message: string }) {
  return (
    <div className="empty-state">
      <Inbox />
      <span>{message}</span>
    </div>
  );
}

export function ErrorState({
  message = "Impossible de charger les données.",
  onRetry,
}: {
  message?: string;
  onRetry?: () => void;
}) {
  return (
    <div className="empty-state" role="alert">
      <CircleAlert />
      <span>{message}</span>
      {onRetry && (
        <button type="button" className="btn btn-ghost btn-sm" onClick={onRetry}>
          Réessayer
        </button>
      )}
    </div>
  );
}

/** Triade chargement / erreur / vide pour les listes React Query. */
export function QueryStatus({
  isLoading,
  isError,
  isEmpty,
  emptyMessage = "Aucun élément.",
  errorMessage,
  onRetry,
  children,
}: {
  isLoading: boolean;
  isError: boolean;
  isEmpty?: boolean;
  emptyMessage?: string;
  errorMessage?: string;
  onRetry?: () => void;
  children: ReactNode;
}) {
  if (isLoading) return <Spinner />;
  if (isError) {
    return <ErrorState message={errorMessage} onRetry={onRetry} />;
  }
  if (isEmpty) return <EmptyState message={emptyMessage} />;
  return <>{children}</>;
}

export function TenantScopeNotice() {
  return (
    <div className="empty-state">
      Ce paramétrage est propre à une filiale. Sélectionnez une filiale dans la
      barre supérieure pour la gérer.
    </div>
  );
}

export function Card({
  title,
  children,
  className,
}: {
  title?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={className ? `card ${className}` : "card"}>
      {title && <div className="card-title">{title}</div>}
      <div className="card-body">{children}</div>
    </div>
  );
}

/** Taille de page alignée sur `PAGE_SIZE` API (DefaultPagination). */
export const DEFAULT_PAGE_SIZE = 25;

export function PaginationBar({
  page,
  count,
  pageSize = DEFAULT_PAGE_SIZE,
  onPageChange,
}: {
  page: number;
  count: number;
  pageSize?: number;
  onPageChange: (page: number) => void;
}) {
  const totalPages = Math.max(1, Math.ceil(count / pageSize));
  if (count <= pageSize) {
    return (
      <p className="pagination-bar muted small">
        {count} élément{count > 1 ? "s" : ""}
      </p>
    );
  }
  const from = (page - 1) * pageSize + 1;
  const to = Math.min(page * pageSize, count);
  return (
    <div className="pagination-bar">
      <span className="muted small">
        {from}–{to} sur {count}
      </span>
      <div className="pagination-actions">
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
        >
          Précédent
        </button>
        <span className="pagination-page muted small">
          Page {page} / {totalPages}
        </span>
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          disabled={page >= totalPages}
          onClick={() => onPageChange(page + 1)}
        >
          Suivant
        </button>
      </div>
    </div>
  );
}

export function formatMoney(value: string | number | null, currency = "XOF") {
  if (value === null || value === undefined) return "—";
  const num = typeof value === "string" ? Number(value) : value;
  return `${num.toLocaleString("fr-FR")} ${currency}`;
}

export function formatDate(value: string | null) {
  if (!value) return "—";
  return new Date(value).toLocaleString("fr-FR", {
    dateStyle: "short",
    timeStyle: "short",
  });
}

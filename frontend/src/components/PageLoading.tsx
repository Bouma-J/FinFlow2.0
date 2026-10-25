export function PageLoading() {
  return (
    <div className="route-loading" role="status">
      <span className="spinner" aria-hidden="true" />
      <span>Chargement de la page…</span>
    </div>
  );
}

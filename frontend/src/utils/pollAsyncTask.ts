import { api } from "@/api/client";

export type AsyncTaskState =
  | "PENDING"
  | "STARTED"
  | "RETRY"
  | "SUCCESS"
  | "FAILURE"
  | "REVOKED"
  | string;

export type AsyncTaskStatus = {
  task_id: string;
  state: AsyncTaskState;
  ready?: boolean;
  detail?: string;
  result?: Record<string, unknown>;
};

/**
 * Interroge /async-tasks/<id>/ jusqu'à SUCCESS, FAILURE ou timeout.
 * `onTick` permet d'invalider les queries React Query entre deux polls.
 */
export async function pollAsyncTask(
  taskId: string,
  opts?: {
    intervalMs?: number;
    maxAttempts?: number;
    onTick?: () => void;
  },
): Promise<AsyncTaskStatus> {
  const intervalMs = opts?.intervalMs ?? 2000;
  const maxAttempts = opts?.maxAttempts ?? 30;

  for (let i = 0; i < maxAttempts; i += 1) {
    opts?.onTick?.();
    const { data } = await api.get<AsyncTaskStatus>(
      `/async-tasks/${encodeURIComponent(taskId)}/`,
    );
    const state = (data.state || "").toUpperCase();
    if (state === "SUCCESS") return data;
    if (
      state === "FAILURE" ||
      state === "REVOKED" ||
      state === "UNKNOWN"
    ) {
      throw new Error(
        data.detail || "La tâche asynchrone a échoué.",
      );
    }
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  throw new Error(
    "Délai dépassé : la tâche n'a pas terminé à temps. Réessayez ou vérifiez le worker Celery.",
  );
}

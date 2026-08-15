import { useSessionStore } from "@/stores/sessionStore";

/** Message shown wherever an analysis is attempted without uploaded data. */
export const NO_SESSION_MESSAGE =
  "No active session. Upload a feature table (and metadata) on the Upload page first.";

/**
 * Resolve the active analysis session.
 *
 * Analysis pages previously hardcoded `sessionId = "mock-session"` — a
 * placeholder that was never wired up — so every request went to
 * `/sessions/mock-session/analyze/...` and 404'd once real data was uploaded.
 *
 * `sessionId` is typed as `string` so existing call sites keep compiling, but it
 * is the empty string when no data has been uploaded. Callers should gate on
 * `hasSession` before firing a request; if one slips through, `runAnalysis` in
 * utils/api.ts rejects the empty id with {@link NO_SESSION_MESSAGE} rather than
 * issuing a request to a nonsense URL.
 */
export function useRequiredSession() {
  const storedSessionId = useSessionStore((state) => state.sessionId);

  return {
    sessionId: storedSessionId ?? "",
    hasSession: Boolean(storedSessionId),
  };
}

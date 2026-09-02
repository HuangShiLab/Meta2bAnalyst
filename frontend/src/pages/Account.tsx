import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Database, Trash2, Loader2, RefreshCw } from "lucide-react";
import api from "@/utils/api";
import { useAuthStore } from "@/stores/authStore";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";

interface UsageInfo {
  used_bytes: number;
  quota_mb: number;
  session_count: number;
}

interface SessionItem {
  id: string;
  name: string | null;
  data_format: string | null;
  status: string;
  file_count: number;
  created_at: string;
  user_id: number | null;
}

function formatMB(bytes: number): string {
  return (bytes / 1024 / 1024).toFixed(1);
}

export function Account() {
  const user = useAuthStore((s) => s.user);
  const [usage, setUsage] = useState<UsageInfo | null>(null);
  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [pwMessage, setPwMessage] = useState<string | null>(null);
  const [pwError, setPwError] = useState<string | null>(null);
  const [pwLoading, setPwLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [usageRes, sessionsRes] = await Promise.all([
        api.get("/auth/me/usage"),
        api.get("/sessions"),
      ]);
      setUsage(usageRes.data as UsageInfo);
      const all = (sessionsRes.data.sessions ?? []) as SessionItem[];
      // Students: the backend already returns only own + shared sessions;
      // keep the shared (demo) ones out of the deletable list.
      setSessions(all.filter((s) => s.file_count >= 0));
    } catch {
      setError("Failed to load your data. Is the backend reachable?");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleDelete = async (sessionId: string) => {
    if (!window.confirm("Delete this session and all its uploaded files?")) return;
    setDeleting(sessionId);
    try {
      await api.delete(`/sessions/${sessionId}`);
      await load();
    } catch {
      setError("Failed to delete the session.");
    } finally {
      setDeleting(null);
    }
  };

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setPwMessage(null);
    setPwError(null);
    setPwLoading(true);
    try {
      await api.post("/auth/change-password", {
        old_password: oldPassword,
        new_password: newPassword,
      });
      setPwMessage("Password changed successfully.");
      setOldPassword("");
      setNewPassword("");
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail;
      setPwError(detail || "Failed to change password.");
    } finally {
      setPwLoading(false);
    }
  };

  const usedMB = usage ? Number(formatMB(usage.used_bytes)) : 0;
  const pct = usage ? Math.min(100, (usedMB / usage.quota_mb) * 100) : 0;

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-6">
      <div className="flex items-center gap-3">
        <Database className="h-6 w-6 text-primary" />
        <h1 className="text-2xl font-bold tracking-tight">My Data</h1>
      </div>

      {error && (
        <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </p>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Account &amp; storage</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-muted-foreground">
            Signed in as{" "}
            <span className="font-medium text-foreground">
              {user?.username ?? "…"}
            </span>{" "}
            ({user?.role ?? "…"})
          </p>
          {usage && (
            <div className="space-y-1.5">
              <div className="flex justify-between text-sm">
                <span>
                  {formatMB(usage.used_bytes)} MB used of {usage.quota_mb} MB
                </span>
                <span className="text-muted-foreground">
                  {usage.session_count} session{usage.session_count === 1 ? "" : "s"}
                </span>
              </div>
              <Progress value={pct} />
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base">My sessions</CardTitle>
          <Button variant="outline" size="sm" onClick={load} disabled={loading}>
            <RefreshCw className={`mr-1.5 h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </CardHeader>
        <CardContent>
          {loading && sessions.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">Loading…</p>
          ) : sessions.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              No sessions yet.{" "}
              <Link to="/upload" className="text-primary underline">
                Upload data
              </Link>{" "}
              to get started.
            </p>
          ) : (
            <ul className="divide-y divide-border">
              {sessions.map((s) => {
                const canDelete =
                  user?.role === "admin" || (user != null && s.user_id === user.id);
                return (
                <li key={s.id} className="flex items-center gap-3 py-3">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">
                      {s.name || "(unnamed session)"}
                      {s.user_id == null && (
                        <span className="ml-2 rounded bg-slate-100 px-1.5 py-0.5 text-xs font-normal text-muted-foreground">
                          shared demo
                        </span>
                      )}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {s.file_count} file{s.file_count === 1 ? "" : "s"} ·{" "}
                      {s.data_format || "unknown format"} · created{" "}
                      {new Date(s.created_at).toLocaleDateString()}
                    </p>
                  </div>
                  <span className="text-xs text-muted-foreground">{s.status}</span>
                  {canDelete && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleDelete(s.id)}
                      disabled={deleting === s.id}
                      title="Delete session"
                    >
                      {deleting === s.id ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Trash2 className="h-4 w-4 text-destructive" />
                      )}
                    </Button>
                  )}
                </li>
                );
              })}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Change password</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleChangePassword} className="max-w-sm space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="old-pw">Current password</Label>
              <Input
                id="old-pw"
                type="password"
                autoComplete="current-password"
                value={oldPassword}
                onChange={(e) => setOldPassword(e.target.value)}
                required
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="new-pw">New password (min 6 characters)</Label>
              <Input
                id="new-pw"
                type="password"
                autoComplete="new-password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                minLength={6}
                required
              />
            </div>
            {pwError && <p className="text-sm text-destructive">{pwError}</p>}
            {pwMessage && <p className="text-sm text-green-600">{pwMessage}</p>}
            <Button type="submit" disabled={pwLoading}>
              {pwLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Change password
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}

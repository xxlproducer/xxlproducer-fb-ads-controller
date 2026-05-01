import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { CheckCircle2, AlertCircle, Trash2, RefreshCw, Plus } from "lucide-react";
import { Layout } from "@/components/Layout";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { api, getApiErrorMessage } from "@/lib/api";
import { cn, formatDate } from "@/lib/utils";

interface Token {
  id: number;
  fb_user_id: string | null;
  fb_user_name: string | null;
  label: string | null;
  granted_scopes: string | null;
  status: string;
  last_error: string | null;
  proxy_url: string | null;
  is_disabled: boolean;
  created_at: string;
  last_synced_at: string | null;
}

interface AccountSummary {
  token_id: number;
  token_label: string | null;
  fb_user_name: string | null;
  id: string;
  name: string | null;
  account_status: number | null;
  currency: string | null;
  timezone_name: string | null;
  balance: string | null;
  amount_spent: string | null;
  business_id: string | null;
  business_name: string | null;
}

const REQUIRED_SCOPES = ["ads_management", "ads_read", "business_management", "read_insights"];

export function Tokens() {
  const qc = useQueryClient();
  const [showAdd, setShowAdd] = useState(false);

  const tokensQ = useQuery({
    queryKey: ["tokens"],
    queryFn: async () => (await api.get<Token[]>("/tokens/")).data,
  });

  const accountsQ = useQuery({
    queryKey: ["fb-accounts"],
    queryFn: async () =>
      (await api.get<{ count: number; accounts: AccountSummary[] }>("/fb-accounts/")).data,
  });

  const addMut = useMutation({
    mutationFn: async (payload: { access_token: string; label?: string; proxy_url?: string }) =>
      (await api.post<Token>("/tokens/", payload)).data,
    onSuccess: (token) => {
      toast.success(`Connected ${token.fb_user_name}`);
      setShowAdd(false);
      qc.invalidateQueries({ queryKey: ["tokens"] });
      qc.invalidateQueries({ queryKey: ["fb-accounts"] });
    },
    onError: (err) => toast.error(getApiErrorMessage(err, "Failed to add token")),
  });

  const syncMut = useMutation({
    mutationFn: async (id: number) => (await api.post<Token>(`/tokens/${id}/sync`)).data,
    onSuccess: () => {
      toast.success("Synced");
      qc.invalidateQueries({ queryKey: ["tokens"] });
      qc.invalidateQueries({ queryKey: ["fb-accounts"] });
    },
    onError: (err) => toast.error(getApiErrorMessage(err)),
  });

  const delMut = useMutation({
    mutationFn: async (id: number) => api.delete(`/tokens/${id}`),
    onSuccess: () => {
      toast.success("Removed");
      qc.invalidateQueries({ queryKey: ["tokens"] });
      qc.invalidateQueries({ queryKey: ["fb-accounts"] });
    },
    onError: (err) => toast.error(getApiErrorMessage(err)),
  });

  const tokens = tokensQ.data ?? [];

  return (
    <Layout
      title="FB Accounts"
      description="Connect your Facebook tokens. All data stays local."
      actions={
        <Button onClick={() => setShowAdd((v) => !v)} size="md">
          <Plus className="h-4 w-4" />
          Connect token
        </Button>
      }
    >
      {showAdd && (
        <div className="mb-6">
          <AddTokenForm
            onCancel={() => setShowAdd(false)}
            onSubmit={(payload) => addMut.mutate(payload)}
            submitting={addMut.isPending}
          />
        </div>
      )}

      {tokensQ.isLoading ? (
        <Card>
          <CardBody>
            <div className="text-sm text-ink-500">Loading…</div>
          </CardBody>
        </Card>
      ) : tokens.length === 0 ? (
        <EmptyState onAdd={() => setShowAdd(true)} />
      ) : (
        <div className="space-y-4">
          {tokens.map((t) => {
            const tokenAccounts = accountsQ.data?.accounts.filter((a) => a.token_id === t.id) ?? [];
            return (
              <TokenCard
                key={t.id}
                token={t}
                accounts={tokenAccounts}
                onSync={() => syncMut.mutate(t.id)}
                onDelete={() => {
                  if (confirm(`Remove token for ${t.fb_user_name ?? t.label}?`)) {
                    delMut.mutate(t.id);
                  }
                }}
                syncing={syncMut.isPending && syncMut.variables === t.id}
                deleting={delMut.isPending && delMut.variables === t.id}
              />
            );
          })}
        </div>
      )}
    </Layout>
  );
}

function EmptyState({ onAdd }: { onAdd: () => void }) {
  return (
    <Card>
      <CardBody className="py-16 text-center">
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-ink-100 dark:bg-ink-700">
          <Plus className="h-5 w-5 text-ink-500" />
        </div>
        <h3 className="text-lg font-semibold tracking-tight">No tokens yet</h3>
        <p className="mx-auto mt-1.5 max-w-md text-sm text-ink-500">
          Connect a long-lived FB user access token to start managing your ad accounts.
        </p>
        <Button className="mt-6" onClick={onAdd}>
          Connect first token
        </Button>
      </CardBody>
    </Card>
  );
}

function AddTokenForm({
  onCancel,
  onSubmit,
  submitting,
}: {
  onCancel: () => void;
  onSubmit: (p: { access_token: string; label?: string; proxy_url?: string }) => void;
  submitting: boolean;
}) {
  const [accessToken, setAccessToken] = useState("");
  const [label, setLabel] = useState("");
  const [proxy, setProxy] = useState("");

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!accessToken.trim()) return;
    onSubmit({
      access_token: accessToken.trim(),
      label: label.trim() || undefined,
      proxy_url: proxy.trim() || undefined,
    });
  }

  return (
    <Card>
      <CardHeader
        title="Connect a Facebook token"
        description="Paste a long-lived user access token with ads_management scope"
      />
      <CardBody>
        <form className="space-y-4" onSubmit={submit}>
          <Input
            label="Access token"
            name="access_token"
            type="password"
            placeholder="EAA…"
            value={accessToken}
            onChange={(e) => setAccessToken(e.target.value)}
            autoFocus
            required
          />
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Input
              label="Label (optional)"
              name="label"
              placeholder="e.g. Farm acc #3"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
            />
            <Input
              label="Proxy URL (optional)"
              name="proxy_url"
              placeholder="http://user:pass@host:port"
              value={proxy}
              onChange={(e) => setProxy(e.target.value)}
              hint="If set, all FB calls for this token go via this proxy"
            />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="ghost" onClick={onCancel} disabled={submitting}>
              Cancel
            </Button>
            <Button type="submit" loading={submitting}>
              Validate &amp; connect
            </Button>
          </div>
        </form>
      </CardBody>
    </Card>
  );
}

function TokenCard({
  token,
  accounts,
  onSync,
  onDelete,
  syncing,
  deleting,
}: {
  token: Token;
  accounts: AccountSummary[];
  onSync: () => void;
  onDelete: () => void;
  syncing: boolean;
  deleting: boolean;
}) {
  const scopes = (token.granted_scopes ?? "").split(",").filter(Boolean);
  const missing = REQUIRED_SCOPES.filter((s) => !scopes.includes(s));
  const ok = token.status === "active" && missing.length === 0;

  return (
    <Card>
      <CardHeader
        title={
          <div className="flex items-center gap-2.5">
            {ok ? (
              <CheckCircle2 className="h-4 w-4 text-success" />
            ) : (
              <AlertCircle className="h-4 w-4 text-warning" />
            )}
            <span>{token.fb_user_name ?? "Unknown user"}</span>
            {token.label && (
              <span className="rounded-md bg-ink-100 px-1.5 py-0.5 text-xs font-normal text-ink-600 dark:bg-ink-700 dark:text-ink-300">
                {token.label}
              </span>
            )}
          </div>
        }
        description={
          <span>
            FB user {token.fb_user_id} · synced {formatDate(token.last_synced_at)}
            {token.proxy_url && <> · via proxy</>}
          </span>
        }
        action={
          <div className="flex gap-2">
            <Button variant="ghost" size="sm" onClick={onSync} loading={syncing} title="Re-validate">
              <RefreshCw className="h-3.5 w-3.5" />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={onDelete}
              loading={deleting}
              className="text-danger hover:bg-danger/10"
              title="Remove"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          </div>
        }
      />
      <CardBody className="space-y-4">
        {token.last_error && (
          <div className="rounded-xl bg-danger/10 px-4 py-3 text-sm text-danger">
            {token.last_error}
          </div>
        )}
        {missing.length > 0 && (
          <div className="rounded-xl bg-warning/10 px-4 py-3 text-sm text-warning">
            Missing scopes: {missing.join(", ")}
          </div>
        )}
        <div className="flex flex-wrap gap-1.5">
          {scopes.map((s) => (
            <span
              key={s}
              className={cn(
                "rounded-md px-2 py-0.5 text-xs",
                REQUIRED_SCOPES.includes(s)
                  ? "bg-success/10 text-success"
                  : "bg-ink-100 text-ink-600 dark:bg-ink-700 dark:text-ink-300",
              )}
            >
              {s}
            </span>
          ))}
        </div>

        <div>
          <div className="mb-2 text-xs font-medium uppercase tracking-wide text-ink-500">
            Ad accounts ({accounts.length})
          </div>
          {accounts.length === 0 ? (
            <div className="text-sm text-ink-500">No ad accounts visible to this token.</div>
          ) : (
            <div className="overflow-hidden rounded-xl border border-ink-100 dark:border-ink-700">
              <table className="w-full text-sm">
                <thead className="bg-ink-50 text-xs uppercase tracking-wide text-ink-500 dark:bg-ink-800/60">
                  <tr>
                    <th className="px-4 py-2 text-left font-medium">Name</th>
                    <th className="px-4 py-2 text-left font-medium">Account ID</th>
                    <th className="px-4 py-2 text-left font-medium">Currency</th>
                    <th className="px-4 py-2 text-left font-medium">Timezone</th>
                    <th className="px-4 py-2 text-right font-medium">Spent</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-ink-100 dark:divide-ink-700">
                  {accounts.map((a) => (
                    <tr key={a.id}>
                      <td className="px-4 py-2.5">{a.name ?? "—"}</td>
                      <td className="px-4 py-2.5 font-mono text-xs text-ink-500">{a.id}</td>
                      <td className="px-4 py-2.5">{a.currency ?? "—"}</td>
                      <td className="px-4 py-2.5 text-ink-500">{a.timezone_name ?? "—"}</td>
                      <td className="px-4 py-2.5 text-right tabular-nums">
                        {a.amount_spent ?? "0"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </CardBody>
    </Card>
  );
}

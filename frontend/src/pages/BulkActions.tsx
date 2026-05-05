import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  Layers,
  Loader2,
  Pause,
  Play,
  RefreshCw,
  Search,
  Trash2,
  X,
  XCircle,
} from "lucide-react";
import { Layout } from "@/components/Layout";
import { Card, CardBody } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { api, getApiErrorMessage } from "@/lib/api";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

type Level = "campaign" | "adset" | "ad";
type Action = "pause" | "activate" | "archive" | "delete";

interface InventoryRow {
  token_id: number;
  token_label: string | null;
  account_id: string;
  object_id: string;
  name: string | null;
  status: string | null;
  effective_status: string | null;
  parent_id: string | null;
  campaign_id: string | null;
}

interface InventoryResponse {
  count: number;
  rows: InventoryRow[];
  errors: Array<{
    token_id: number;
    token_label: string | null;
    account_id: string | null;
    error: string;
    code: number | null;
  }>;
}

interface MutationResult {
  object_id: string;
  token_id: number;
  ok: boolean;
  error: string | null;
}

interface MutationResponse {
  total: number;
  succeeded: number;
  failed: number;
  results: MutationResult[];
}

const LEVELS: { id: Level; label: string }[] = [
  { id: "campaign", label: "Campaigns" },
  { id: "adset", label: "Adsets" },
  { id: "ad", label: "Ads" },
];

const STATUS_FILTERS: { id: string; label: string }[] = [
  { id: "ALL", label: "All" },
  { id: "ACTIVE", label: "Active" },
  { id: "PAUSED", label: "Paused" },
  { id: "ARCHIVED", label: "Archived" },
];

export function BulkActions() {
  const qc = useQueryClient();
  const [level, setLevel] = useState<Level>("campaign");
  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [pendingAction, setPendingAction] = useState<Action | null>(null);
  const [confirmText, setConfirmText] = useState("");
  const [resultData, setResultData] = useState<MutationResponse | null>(null);

  const inventoryQ = useQuery({
    queryKey: ["bulk-inventory", level],
    queryFn: async () => {
      try {
        const { data } = await api.post<InventoryResponse>("/bulk/inventory", {
          level,
        });
        return data;
      } catch (err) {
        toast.error(getApiErrorMessage(err, "Failed to load inventory"));
        throw err;
      }
    },
    staleTime: 30_000,
  });

  // Reset selection when level changes — different ID space.
  useEffect(() => {
    setSelected(new Set());
  }, [level]);

  const rows = inventoryQ.data?.rows ?? [];
  const errors = inventoryQ.data?.errors ?? [];

  const filtered = useMemo(() => {
    let r = rows;
    if (statusFilter !== "ALL") {
      r = r.filter((x) => (x.effective_status || "").toUpperCase() === statusFilter);
    }
    if (search.trim()) {
      const q = search.toLowerCase();
      r = r.filter(
        (x) =>
          (x.name || "").toLowerCase().includes(q) ||
          x.object_id.includes(q) ||
          x.account_id.includes(q) ||
          (x.token_label || "").toLowerCase().includes(q),
      );
    }
    return r;
  }, [rows, statusFilter, search]);

  // Build a key from object_id+token_id since the same id can in theory exist
  // under different tokens (won't, in practice, but safe).
  const keyOf = (r: InventoryRow) => `${r.token_id}:${r.object_id}`;
  const selectedRows = useMemo(
    () => filtered.filter((r) => selected.has(keyOf(r))),
    [filtered, selected],
  );

  const allSelected = filtered.length > 0 && selectedRows.length === filtered.length;
  const someSelected = selectedRows.length > 0 && !allSelected;

  const toggleAll = () => {
    if (allSelected) {
      setSelected(new Set());
    } else {
      setSelected(new Set(filtered.map(keyOf)));
    }
  };

  const toggleOne = (r: InventoryRow) => {
    const k = keyOf(r);
    const next = new Set(selected);
    if (next.has(k)) next.delete(k);
    else next.add(k);
    setSelected(next);
  };

  const mutateM = useMutation({
    mutationFn: async (action: Action) => {
      const targets = selectedRows.map((r) => ({
        token_id: r.token_id,
        object_id: r.object_id,
        account_id: r.account_id,
      }));
      const url = action === "delete" ? "/bulk/delete" : "/bulk/update_status";
      const body =
        action === "delete"
          ? { level, targets }
          : { action, level, targets };
      const { data } = await api.post<MutationResponse>(url, body);
      return data;
    },
    onSuccess: (data, action) => {
      setResultData(data);
      setPendingAction(null);
      setConfirmText("");
      if (data.failed === 0) {
        toast.success(`${actionLabel(action)} ${data.succeeded} object${data.succeeded === 1 ? "" : "s"}`);
      } else {
        toast.error(`${data.failed} of ${data.total} failed`);
      }
      // Clear selection of successfully mutated objects only
      const failedIds = new Set(data.results.filter((r) => !r.ok).map((r) => `${r.token_id}:${r.object_id}`));
      setSelected(failedIds);
      qc.invalidateQueries({ queryKey: ["bulk-inventory", level] });
    },
    onError: (err) => {
      toast.error(getApiErrorMessage(err, "Bulk action failed"));
      setPendingAction(null);
      setConfirmText("");
    },
  });

  const requestAction = (action: Action) => {
    if (selectedRows.length === 0) return;
    setPendingAction(action);
    setConfirmText("");
  };

  const confirmAndRun = () => {
    if (!pendingAction) return;
    if (pendingAction === "delete" && selectedRows.length >= 10) {
      if (confirmText.trim().toUpperCase() !== "DELETE") {
        toast.error('Type DELETE to confirm');
        return;
      }
    }
    mutateM.mutate(pendingAction);
  };

  return (
    <Layout
      title="Bulk Actions"
      description="Pause, activate, or delete campaigns / adsets / ads in batch"
      actions={
        <Button
          onClick={() => inventoryQ.refetch()}
          loading={inventoryQ.isFetching}
          size="md"
          variant="ghost"
        >
          <RefreshCw className="h-4 w-4" />
          Refresh
        </Button>
      }
    >
      {/* Filter bar */}
      <Card className="mb-6">
        <CardBody className="space-y-4">
          <div className="flex flex-wrap items-center gap-4">
            <div className="flex items-center gap-2">
              <span className="text-xs uppercase tracking-wider text-ink-500">
                Level
              </span>
              <div className="flex rounded-xl bg-ink-100 p-0.5 dark:bg-ink-800">
                {LEVELS.map((l) => (
                  <button
                    key={l.id}
                    onClick={() => setLevel(l.id)}
                    className={cn(
                      "rounded-lg px-3 py-1 text-xs font-medium transition-all",
                      level === l.id
                        ? "bg-white text-ink-900 shadow-sm dark:bg-ink-700 dark:text-ink-100"
                        : "text-ink-600 hover:text-ink-900 dark:text-ink-400 dark:hover:text-ink-200",
                    )}
                  >
                    {l.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex flex-wrap gap-1.5">
              {STATUS_FILTERS.map((s) => (
                <button
                  key={s.id}
                  onClick={() => setStatusFilter(s.id)}
                  className={cn(
                    "rounded-full px-3 py-1 text-xs font-medium transition-all",
                    statusFilter === s.id
                      ? "bg-accent text-white shadow-card"
                      : "bg-ink-100 text-ink-700 hover:bg-ink-200/70 dark:bg-ink-800 dark:text-ink-300 dark:hover:bg-ink-700",
                  )}
                >
                  {s.label}
                </button>
              ))}
            </div>

            <div className="ml-auto flex-1 max-w-xs">
              <div className="relative">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-400" />
                <input
                  type="search"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search by name or id…"
                  className="w-full rounded-xl border border-ink-200/80 bg-white py-1.5 pl-9 pr-3 text-sm placeholder:text-ink-400 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20 dark:border-ink-700 dark:bg-ink-800 dark:placeholder:text-ink-500"
                />
              </div>
            </div>
          </div>
        </CardBody>
      </Card>

      {/* Errors panel */}
      {errors.length > 0 && (
        <Card className="mb-4 border-amber-200/60 bg-amber-50/60 dark:border-amber-900/40 dark:bg-amber-950/20">
          <CardBody>
            <div className="text-xs font-medium uppercase tracking-wider text-amber-700 dark:text-amber-500">
              {errors.length} account{errors.length > 1 ? "s" : ""} returned errors
            </div>
            <ul className="mt-2 space-y-1 text-xs text-amber-800 dark:text-amber-400">
              {errors.slice(0, 5).map((e, i) => (
                <li key={i}>
                  {e.account_id ? `act_${e.account_id}` : (e.token_label || `token #${e.token_id}`)}: {e.error}
                </li>
              ))}
              {errors.length > 5 && <li>+{errors.length - 5} more…</li>}
            </ul>
          </CardBody>
        </Card>
      )}

      {/* Table */}
      <Card>
        {inventoryQ.isLoading ? (
          <CardBody>
            <div className="flex items-center gap-2 text-sm text-ink-500">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading inventory…
            </div>
          </CardBody>
        ) : filtered.length === 0 ? (
          <CardBody className="py-16 text-center">
            <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-ink-100 dark:bg-ink-700">
              <Layers className="h-5 w-5 text-ink-500" />
            </div>
            <h3 className="text-lg font-semibold tracking-tight">
              No {level}s match the current filter
            </h3>
            <p className="mt-1 text-sm text-ink-500">
              Switch level, status filter, or search term — or refresh to re-pull from FB.
            </p>
          </CardBody>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-ink-200/60 text-left text-xs uppercase tracking-wider text-ink-500 dark:border-ink-700/60">
                  <th className="w-10 px-4 py-3">
                    <input
                      type="checkbox"
                      checked={allSelected}
                      ref={(el) => {
                        if (el) el.indeterminate = someSelected;
                      }}
                      onChange={toggleAll}
                      className="h-4 w-4 cursor-pointer rounded border-ink-300 accent-accent"
                    />
                  </th>
                  <th className="px-4 py-3">Name</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Account</th>
                  <th className="px-4 py-3">Token</th>
                  <th className="px-4 py-3 text-right">ID</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((r) => {
                  const isSel = selected.has(keyOf(r));
                  return (
                    <tr
                      key={keyOf(r)}
                      onClick={() => toggleOne(r)}
                      className={cn(
                        "cursor-pointer border-b border-ink-100/60 transition-colors dark:border-ink-800/60",
                        isSel
                          ? "bg-accent/5 dark:bg-accent/10"
                          : "hover:bg-ink-50/60 dark:hover:bg-ink-800/40",
                      )}
                    >
                      <td className="px-4 py-3">
                        <input
                          type="checkbox"
                          checked={isSel}
                          onChange={(e) => {
                            e.stopPropagation();
                            toggleOne(r);
                          }}
                          onClick={(e) => e.stopPropagation()}
                          className="h-4 w-4 cursor-pointer rounded border-ink-300 accent-accent"
                        />
                      </td>
                      <td className="px-4 py-3">
                        <div className="font-medium tracking-tight">
                          {r.name || <span className="text-ink-400">—</span>}
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <StatusBadge status={r.effective_status || r.status} />
                      </td>
                      <td className="px-4 py-3 font-mono text-xs text-ink-600 dark:text-ink-400">
                        act_{r.account_id}
                      </td>
                      <td className="px-4 py-3 text-xs text-ink-600 dark:text-ink-400">
                        {r.token_label || `#${r.token_id}`}
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-xs text-ink-500">
                        {r.object_id}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Action bar (sticky bottom) */}
      {selectedRows.length > 0 && (
        <div className="sticky bottom-4 z-20 mt-6 animate-slide-up">
          <Card className="border-accent/30 bg-white/95 shadow-glass backdrop-blur dark:bg-ink-800/95">
            <CardBody className="flex flex-wrap items-center gap-3">
              <div className="flex items-center gap-2 text-sm font-medium">
                <span className="rounded-full bg-accent/10 px-2.5 py-0.5 text-xs font-semibold text-accent">
                  {selectedRows.length}
                </span>
                {level}
                {selectedRows.length === 1 ? "" : "s"} selected
              </div>
              <div className="ml-auto flex flex-wrap gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setSelected(new Set())}
                >
                  Clear
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => requestAction("activate")}
                >
                  <Play className="h-3.5 w-3.5" />
                  Activate
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => requestAction("pause")}
                >
                  <Pause className="h-3.5 w-3.5" />
                  Pause
                </Button>
                <Button
                  variant="danger"
                  size="sm"
                  onClick={() => requestAction("delete")}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  Delete
                </Button>
              </div>
            </CardBody>
          </Card>
        </div>
      )}

      {/* Confirm modal */}
      {pendingAction && (
        <Modal onClose={() => !mutateM.isPending && setPendingAction(null)}>
          <div className="flex items-start gap-3">
            <div
              className={cn(
                "flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full",
                pendingAction === "delete"
                  ? "bg-danger/10 text-danger"
                  : "bg-accent/10 text-accent",
              )}
            >
              {pendingAction === "delete" ? (
                <AlertTriangle className="h-5 w-5" />
              ) : pendingAction === "activate" ? (
                <Play className="h-5 w-5" />
              ) : (
                <Pause className="h-5 w-5" />
              )}
            </div>
            <div className="flex-1">
              <h3 className="text-base font-semibold tracking-tight">
                {actionLabel(pendingAction)} {selectedRows.length} {level}
                {selectedRows.length === 1 ? "" : "s"}?
              </h3>
              <p className="mt-1 text-sm text-ink-500">
                {pendingAction === "delete"
                  ? "This permanently removes the objects on Facebook. This cannot be undone."
                  : `Each ${level} will be set to ${pendingAction === "pause" ? "PAUSED" : "ACTIVE"}.`}
              </p>
              {pendingAction === "delete" && selectedRows.length >= 10 && (
                <div className="mt-3">
                  <label className="text-xs font-medium uppercase tracking-wider text-ink-500">
                    Type DELETE to confirm
                  </label>
                  <input
                    autoFocus
                    type="text"
                    value={confirmText}
                    onChange={(e) => setConfirmText(e.target.value)}
                    className="mt-1 w-full rounded-xl border border-ink-200/80 bg-white px-3 py-2 text-sm focus:border-danger focus:outline-none focus:ring-2 focus:ring-danger/20 dark:border-ink-700 dark:bg-ink-900"
                    placeholder="DELETE"
                  />
                </div>
              )}
            </div>
          </div>
          <div className="mt-6 flex justify-end gap-2">
            <Button
              variant="secondary"
              size="md"
              onClick={() => setPendingAction(null)}
              disabled={mutateM.isPending}
            >
              Cancel
            </Button>
            <Button
              variant={pendingAction === "delete" ? "danger" : "primary"}
              size="md"
              onClick={confirmAndRun}
              loading={mutateM.isPending}
            >
              {actionLabel(pendingAction)}
            </Button>
          </div>
        </Modal>
      )}

      {/* Result modal */}
      {resultData && !pendingAction && (
        <Modal onClose={() => setResultData(null)}>
          <div className="flex items-start gap-3">
            <div
              className={cn(
                "flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full",
                resultData.failed === 0 ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700",
              )}
            >
              {resultData.failed === 0 ? (
                <CheckCircle2 className="h-5 w-5" />
              ) : (
                <AlertTriangle className="h-5 w-5" />
              )}
            </div>
            <div className="flex-1">
              <h3 className="text-base font-semibold tracking-tight">
                {resultData.succeeded} succeeded
                {resultData.failed > 0 && `, ${resultData.failed} failed`}
              </h3>
              {resultData.failed > 0 && (
                <ul className="mt-3 max-h-64 space-y-1 overflow-y-auto text-xs">
                  {resultData.results
                    .filter((r) => !r.ok)
                    .map((r) => (
                      <li
                        key={r.object_id}
                        className="flex items-start gap-2 rounded-lg bg-ink-50 px-2.5 py-1.5 dark:bg-ink-800"
                      >
                        <XCircle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-danger" />
                        <div>
                          <span className="font-mono text-ink-600 dark:text-ink-400">
                            {r.object_id}
                          </span>
                          <span className="ml-2 text-ink-500">{r.error}</span>
                        </div>
                      </li>
                    ))}
                </ul>
              )}
            </div>
          </div>
          <div className="mt-6 flex justify-end">
            <Button variant="primary" size="md" onClick={() => setResultData(null)}>
              Done
            </Button>
          </div>
        </Modal>
      )}
    </Layout>
  );
}

function actionLabel(a: Action): string {
  switch (a) {
    case "pause":
      return "Pause";
    case "activate":
      return "Activate";
    case "archive":
      return "Archive";
    case "delete":
      return "Delete";
  }
}

function StatusBadge({ status }: { status: string | null }) {
  const s = (status || "").toUpperCase();
  const tone =
    s === "ACTIVE"
      ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400"
      : s === "PAUSED"
      ? "bg-ink-100 text-ink-700 dark:bg-ink-800 dark:text-ink-300"
      : s === "ARCHIVED" || s === "DELETED"
      ? "bg-ink-100 text-ink-500 dark:bg-ink-800 dark:text-ink-500"
      : s.includes("DISAPPROVED") || s.includes("REJECTED")
      ? "bg-rose-100 text-rose-700 dark:bg-rose-950/40 dark:text-rose-400"
      : "bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-400";
  return (
    <span className={cn("inline-flex rounded-full px-2 py-0.5 text-[11px] font-medium tracking-tight", tone)}>
      {s || "UNKNOWN"}
    </span>
  );
}

function Modal({ children, onClose }: { children: React.ReactNode; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink-900/40 p-4 backdrop-blur-sm">
      <div className="w-full max-w-md animate-slide-up">
        <Card className="relative">
          <CardBody>
            <button
              onClick={onClose}
              className="absolute right-3 top-3 rounded-full p-1 text-ink-400 hover:bg-ink-100 hover:text-ink-700 dark:hover:bg-ink-800"
              aria-label="Close"
            >
              <X className="h-4 w-4" />
            </button>
            {children}
          </CardBody>
        </Card>
      </div>
    </div>
  );
}

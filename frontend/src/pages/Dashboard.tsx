import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowDownUp,
  ArrowDown,
  ArrowUp,
  Calendar,
  RefreshCw,
  TrendingUp,
  MousePointerClick,
  ShoppingCart,
  Eye,
  Wallet,
  Target,
} from "lucide-react";
import { Layout } from "@/components/Layout";
import { Card, CardBody } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { api, getApiErrorMessage } from "@/lib/api";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

type DatePreset =
  | "today"
  | "yesterday"
  | "this_week_mon_today"
  | "last_7d"
  | "last_14d"
  | "last_30d"
  | "last_90d"
  | "this_month"
  | "last_month";

type Level = "account" | "campaign" | "adset" | "ad";

interface DashboardRow {
  token_id: number;
  token_label: string | null;
  account_id: string | null;
  account_name: string | null;
  campaign_id: string | null;
  campaign_name: string | null;
  adset_id: string | null;
  adset_name: string | null;
  ad_id: string | null;
  ad_name: string | null;
  impressions: number | null;
  reach: number | null;
  clicks: number | null;
  spend: number | null;
  cpm: number | null;
  cpc: number | null;
  ctr: number | null;
  frequency: number | null;
  results: number | null;
  purchases: number | null;
  purchase_value: number | null;
  roas: number | null;
  cost_per_purchase: number | null;
}

interface DashboardResponse {
  count: number;
  rows: DashboardRow[];
  errors: Array<{
    token_id: number;
    token_label: string | null;
    account_id: string | null;
    error: string;
    code: number | null;
  }>;
}

const PRESETS: { id: DatePreset; label: string }[] = [
  { id: "today", label: "Today" },
  { id: "yesterday", label: "Yesterday" },
  { id: "last_7d", label: "Last 7 days" },
  { id: "last_14d", label: "Last 14 days" },
  { id: "last_30d", label: "Last 30 days" },
  { id: "this_month", label: "This month" },
  { id: "last_month", label: "Last month" },
];

const LEVELS: { id: Level; label: string }[] = [
  { id: "account", label: "Account" },
  { id: "campaign", label: "Campaign" },
  { id: "adset", label: "Adset" },
  { id: "ad", label: "Ad" },
];

export function Dashboard() {
  const [datePreset, setDatePreset] = useState<DatePreset>("last_7d");
  const [level, setLevel] = useState<Level>("campaign");
  const [search, setSearch] = useState("");

  const dashboardQ = useQuery({
    queryKey: ["dashboard", datePreset, level],
    queryFn: async () => {
      try {
        const { data } = await api.post<DashboardResponse>("/dashboard/rows", {
          date_preset: datePreset,
          level,
        });
        return data;
      } catch (err) {
        toast.error(getApiErrorMessage(err, "Failed to load dashboard"));
        throw err;
      }
    },
    staleTime: 15_000,
  });

  const rows = dashboardQ.data?.rows ?? [];
  const errors = dashboardQ.data?.errors ?? [];

  const filtered = useMemo(() => {
    if (!search.trim()) return rows;
    const q = search.toLowerCase();
    return rows.filter((r) =>
      [r.account_name, r.campaign_name, r.adset_name, r.ad_name, r.token_label]
        .some((v) => (v ?? "").toLowerCase().includes(q)),
    );
  }, [rows, search]);

  const totals = useMemo(() => {
    const t = {
      spend: 0,
      impressions: 0,
      clicks: 0,
      purchases: 0,
      purchase_value: 0,
      reach: 0,
    };
    for (const r of filtered) {
      t.spend += r.spend ?? 0;
      t.impressions += r.impressions ?? 0;
      t.clicks += r.clicks ?? 0;
      t.purchases += r.purchases ?? 0;
      t.purchase_value += r.purchase_value ?? 0;
      t.reach += r.reach ?? 0;
    }
    return {
      ...t,
      ctr: t.impressions > 0 ? (t.clicks / t.impressions) * 100 : 0,
      cpm: t.impressions > 0 ? (t.spend / t.impressions) * 1000 : 0,
      cpc: t.clicks > 0 ? t.spend / t.clicks : 0,
      roas: t.spend > 0 ? t.purchase_value / t.spend : 0,
      cpp: t.purchases > 0 ? t.spend / t.purchases : 0,
    };
  }, [filtered]);

  return (
    <Layout
      title="Dashboard"
      description="Aggregated metrics across all your ad accounts"
      actions={
        <Button onClick={() => dashboardQ.refetch()} loading={dashboardQ.isFetching} size="md" variant="ghost">
          <RefreshCw className="h-4 w-4" />
          Refresh
        </Button>
      }
    >
      {/* Filter bar */}
      <Card className="mb-6">
        <CardBody className="space-y-4">
          <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-ink-500">
            <Calendar className="h-3.5 w-3.5" />
            Date range
          </div>
          <div className="flex flex-wrap gap-2">
            {PRESETS.map((p) => (
              <button
                key={p.id}
                onClick={() => setDatePreset(p.id)}
                className={cn(
                  "rounded-full px-3.5 py-1.5 text-xs font-medium tracking-tight transition-all",
                  datePreset === p.id
                    ? "bg-accent text-white shadow-card"
                    : "bg-ink-100 text-ink-700 hover:bg-ink-200/70 dark:bg-ink-800 dark:text-ink-300 dark:hover:bg-ink-700",
                )}
              >
                {p.label}
              </button>
            ))}
          </div>

          <div className="flex flex-wrap items-center gap-4 border-t border-ink-200/60 pt-4 dark:border-ink-700/60">
            <div className="flex items-center gap-2">
              <span className="text-xs uppercase tracking-wider text-ink-500">
                Group by
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

            <div className="ml-auto flex-1 max-w-xs">
              <input
                type="search"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search by name…"
                className="w-full rounded-xl border border-ink-200/80 bg-white px-3 py-1.5 text-sm placeholder:text-ink-400 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20 dark:border-ink-700 dark:bg-ink-800 dark:placeholder:text-ink-500"
              />
            </div>
          </div>
        </CardBody>
      </Card>

      {/* KPI row */}
      <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
        <KpiCard icon={Wallet} label="Spend" value={fmtCurrency(totals.spend)} />
        <KpiCard icon={Eye} label="Impressions" value={fmtInt(totals.impressions)} />
        <KpiCard icon={MousePointerClick} label="Clicks" value={fmtInt(totals.clicks)} sub={`CTR ${totals.ctr.toFixed(2)}%`} />
        <KpiCard icon={ShoppingCart} label="Purchases" value={fmtInt(totals.purchases)} sub={totals.cpp ? `CPA ${fmtCurrency(totals.cpp)}` : undefined} />
        <KpiCard icon={TrendingUp} label="Revenue" value={fmtCurrency(totals.purchase_value)} />
        <KpiCard icon={Target} label="ROAS" value={totals.roas ? `${totals.roas.toFixed(2)}x` : "—"} highlight={totals.roas > 1} />
      </div>

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
        {dashboardQ.isLoading ? (
          <CardBody>
            <div className="text-sm text-ink-500">Loading insights…</div>
          </CardBody>
        ) : filtered.length === 0 ? (
          <CardBody className="py-16 text-center">
            <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-ink-100 dark:bg-ink-700">
              <TrendingUp className="h-5 w-5 text-ink-500" />
            </div>
            <h3 className="text-lg font-semibold tracking-tight">No data for this window</h3>
            <p className="mt-1 text-sm text-ink-500">
              Try a wider date range or check that your tokens have active campaigns
            </p>
          </CardBody>
        ) : (
          <DashboardTable rows={filtered} level={level} />
        )}
      </Card>
    </Layout>
  );
}

function KpiCard({
  icon: Icon,
  label,
  value,
  sub,
  highlight,
}: {
  icon: typeof Wallet;
  label: string;
  value: string;
  sub?: string;
  highlight?: boolean;
}) {
  return (
    <Card>
      <CardBody className="space-y-1.5">
        <div className="flex items-center gap-1.5 text-[11px] uppercase tracking-wider text-ink-500">
          <Icon className="h-3.5 w-3.5" />
          {label}
        </div>
        <div
          className={cn(
            "text-xl font-semibold tracking-tight tabular-nums",
            highlight && "text-emerald-600 dark:text-emerald-400",
          )}
        >
          {value}
        </div>
        {sub && <div className="text-[11px] text-ink-500">{sub}</div>}
      </CardBody>
    </Card>
  );
}

type SortKey =
  | "spend"
  | "impressions"
  | "clicks"
  | "ctr"
  | "cpc"
  | "cpm"
  | "purchases"
  | "purchase_value"
  | "roas"
  | "cost_per_purchase";

function DashboardTable({ rows, level }: { rows: DashboardRow[]; level: Level }) {
  const [sortKey, setSortKey] = useState<SortKey>("spend");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const sorted = useMemo(() => {
    const arr = [...rows];
    arr.sort((a, b) => {
      const av = (a[sortKey] ?? -Infinity) as number;
      const bv = (b[sortKey] ?? -Infinity) as number;
      const d = av - bv;
      return sortDir === "asc" ? d : -d;
    });
    return arr;
  }, [rows, sortKey, sortDir]);

  function toggleSort(k: SortKey) {
    if (sortKey === k) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(k);
      setSortDir("desc");
    }
  }

  function nameCell(r: DashboardRow): { primary: string; secondary?: string } {
    if (level === "account") {
      return { primary: r.account_name ?? `act_${r.account_id}`, secondary: `act_${r.account_id}` };
    }
    if (level === "campaign") {
      return { primary: r.campaign_name ?? "—", secondary: r.account_name ?? undefined };
    }
    if (level === "adset") {
      return { primary: r.adset_name ?? "—", secondary: r.campaign_name ?? undefined };
    }
    return { primary: r.ad_name ?? "—", secondary: r.adset_name ?? undefined };
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-ink-200/60 text-left text-[11px] uppercase tracking-wider text-ink-500 dark:border-ink-700/60">
            <th className="px-4 py-3 font-medium">{LEVELS.find((l) => l.id === level)?.label ?? "Name"}</th>
            <SortHeader k="spend" sortKey={sortKey} sortDir={sortDir} onClick={toggleSort} align="right">
              Spend
            </SortHeader>
            <SortHeader k="impressions" sortKey={sortKey} sortDir={sortDir} onClick={toggleSort} align="right">
              Impr.
            </SortHeader>
            <SortHeader k="clicks" sortKey={sortKey} sortDir={sortDir} onClick={toggleSort} align="right">
              Clicks
            </SortHeader>
            <SortHeader k="ctr" sortKey={sortKey} sortDir={sortDir} onClick={toggleSort} align="right">
              CTR
            </SortHeader>
            <SortHeader k="cpc" sortKey={sortKey} sortDir={sortDir} onClick={toggleSort} align="right">
              CPC
            </SortHeader>
            <SortHeader k="cpm" sortKey={sortKey} sortDir={sortDir} onClick={toggleSort} align="right">
              CPM
            </SortHeader>
            <SortHeader k="purchases" sortKey={sortKey} sortDir={sortDir} onClick={toggleSort} align="right">
              Purchases
            </SortHeader>
            <SortHeader k="cost_per_purchase" sortKey={sortKey} sortDir={sortDir} onClick={toggleSort} align="right">
              CPA
            </SortHeader>
            <SortHeader k="roas" sortKey={sortKey} sortDir={sortDir} onClick={toggleSort} align="right">
              ROAS
            </SortHeader>
          </tr>
        </thead>
        <tbody>
          {sorted.map((r, i) => {
            const nm = nameCell(r);
            return (
              <tr
                key={`${r.account_id}-${r.campaign_id}-${r.adset_id}-${r.ad_id}-${i}`}
                className="border-b border-ink-100/80 transition-colors hover:bg-ink-50/60 dark:border-ink-800/60 dark:hover:bg-ink-800/40"
              >
                <td className="px-4 py-3">
                  <div className="font-medium tracking-tight">{nm.primary}</div>
                  {nm.secondary && (
                    <div className="text-[11px] text-ink-500">{nm.secondary}</div>
                  )}
                </td>
                <td className="px-4 py-3 text-right tabular-nums">{fmtCurrency(r.spend)}</td>
                <td className="px-4 py-3 text-right tabular-nums">{fmtInt(r.impressions)}</td>
                <td className="px-4 py-3 text-right tabular-nums">{fmtInt(r.clicks)}</td>
                <td className="px-4 py-3 text-right tabular-nums">{fmtPct(r.ctr)}</td>
                <td className="px-4 py-3 text-right tabular-nums">{fmtCurrency(r.cpc)}</td>
                <td className="px-4 py-3 text-right tabular-nums">{fmtCurrency(r.cpm)}</td>
                <td className="px-4 py-3 text-right tabular-nums">{fmtInt(r.purchases)}</td>
                <td className="px-4 py-3 text-right tabular-nums">{fmtCurrency(r.cost_per_purchase)}</td>
                <td
                  className={cn(
                    "px-4 py-3 text-right font-semibold tabular-nums",
                    (r.roas ?? 0) >= 1 && "text-emerald-600 dark:text-emerald-400",
                    (r.roas ?? 0) > 0 && (r.roas ?? 0) < 1 && "text-rose-600 dark:text-rose-400",
                  )}
                >
                  {r.roas ? `${r.roas.toFixed(2)}x` : "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function SortHeader({
  k,
  sortKey,
  sortDir,
  onClick,
  align,
  children,
}: {
  k: SortKey;
  sortKey: SortKey;
  sortDir: "asc" | "desc";
  onClick: (k: SortKey) => void;
  align?: "left" | "right";
  children: React.ReactNode;
}) {
  const active = sortKey === k;
  return (
    <th
      className={cn(
        "select-none px-4 py-3 font-medium",
        align === "right" ? "text-right" : "text-left",
      )}
    >
      <button
        onClick={() => onClick(k)}
        className={cn(
          "inline-flex items-center gap-1 transition-colors",
          align === "right" ? "flex-row-reverse" : "flex-row",
          active ? "text-ink-900 dark:text-ink-100" : "hover:text-ink-700 dark:hover:text-ink-300",
        )}
      >
        {children}
        {active ? (
          sortDir === "desc" ? (
            <ArrowDown className="h-3 w-3" />
          ) : (
            <ArrowUp className="h-3 w-3" />
          )
        ) : (
          <ArrowDownUp className="h-3 w-3 opacity-40" />
        )}
      </button>
    </th>
  );
}

// ----- formatters

function fmtInt(v: number | null | undefined): string {
  if (v == null) return "—";
  return Math.round(v).toLocaleString();
}

function fmtCurrency(v: number | null | undefined): string {
  if (v == null || v === 0) return v === 0 ? "0" : "—";
  return v.toLocaleString(undefined, {
    minimumFractionDigits: v >= 100 ? 0 : 2,
    maximumFractionDigits: 2,
  });
}

function fmtPct(v: number | null | undefined): string {
  if (v == null) return "—";
  return `${v.toFixed(2)}%`;
}

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  Edit3,
  FileText,
  Loader2,
  Plus,
  Rocket,
  Trash2,
  X,
  XCircle,
} from "lucide-react";
import { toast } from "sonner";
import { Layout } from "@/components/Layout";
import { Card, CardBody } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { api, getApiErrorMessage } from "@/lib/api";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------- types

interface Targeting {
  countries: string[];
  age_min: number;
  age_max: number;
  genders: number[]; // [] = all, [1]=male, [2]=female
  locales: number[];
  publisher_platforms: string[];
}

interface PromotedObject {
  pixel_id?: string | null;
  custom_event_type?: string | null;
  application_id?: string | null;
  object_store_url?: string | null;
}

interface CampaignConfig {
  objective: string;
  status: "PAUSED" | "ACTIVE";
  special_ad_categories: string[];
  buying_type: string;
  daily_budget: number | null;
  lifetime_budget: number | null;
  bid_strategy: string | null;
}

interface AdSetConfig {
  optimization_goal: string;
  billing_event: string;
  status: "PAUSED" | "ACTIVE";
  daily_budget: number | null;
  lifetime_budget: number | null;
  bid_amount: number | null;
  targeting: Targeting;
  promoted_object: PromotedObject | null;
  destination_type: string | null;
  start_time: string | null;
  end_time: string | null;
  dsa_beneficiary: string | null;
  dsa_payor: string | null;
}

interface TemplateConfig {
  campaign: CampaignConfig;
  adset: AdSetConfig;
}

interface Template {
  id: number;
  name: string;
  description: string | null;
  config: TemplateConfig;
  created_at: string;
  updated_at: string;
}

interface AdAccount {
  token_id: number;
  token_label: string | null;
  fb_user_name: string | null;
  id: string;          // numeric id without act_
  name: string | null;
  currency: string | null;
  timezone_name: string | null;
  balance: string | null;
  amount_spent: string | null;
}

interface PreviewRow {
  token_id: number;
  account_id: string;
  account_name: string | null;
  currency: string | null;
  campaign_name: string;
  adset_name: string;
  objective: string;
  daily_budget: number | null;
  optimization_goal: string;
  targeting_summary: string;
}

interface PreviewResponse {
  plan: PreviewRow[];
  warnings: string[];
}

interface LaunchResult {
  token_id: number;
  account_id: string;
  ok: boolean;
  campaign_id: string | null;
  adset_id: string | null;
  error: string | null;
}

interface LaunchResponse {
  results: LaunchResult[];
}

// ---------------------------------------------------------------- defaults

const OBJECTIVES = [
  "OUTCOME_AWARENESS",
  "OUTCOME_TRAFFIC",
  "OUTCOME_ENGAGEMENT",
  "OUTCOME_LEADS",
  "OUTCOME_APP_PROMOTION",
  "OUTCOME_SALES",
];

const OPTIMIZATION_GOALS = [
  "REACH",
  "IMPRESSIONS",
  "LINK_CLICKS",
  "POST_ENGAGEMENT",
  "PAGE_LIKES",
  "OFFSITE_CONVERSIONS",
  "VALUE",
  "LANDING_PAGE_VIEWS",
  "THRUPLAY",
  "LEAD_GENERATION",
  "QUALITY_LEAD",
  "EVENT_RESPONSES",
  "AD_RECALL_LIFT",
  "APP_INSTALLS",
];

const BILLING_EVENTS = [
  "IMPRESSIONS",
  "LINK_CLICKS",
  "PAGE_LIKES",
  "POST_ENGAGEMENT",
];

const BID_STRATEGIES = [
  "LOWEST_COST_WITHOUT_CAP",
  "LOWEST_COST_WITH_BID_CAP",
  "COST_CAP",
];

const CUSTOM_EVENT_TYPES = [
  "PURCHASE",
  "LEAD",
  "COMPLETE_REGISTRATION",
  "ADD_TO_CART",
  "INITIATED_CHECKOUT",
  "ADD_PAYMENT_INFO",
  "VIEW_CONTENT",
  "OTHER",
];

/**
 * Goal presets — pick one and we auto-fill compatible
 * `objective` + `optimization_goal` + `billing_event` + (optionally)
 * the promoted_object skeleton, so the user doesn't have to memorize
 * which combos FB allows.
 *
 * Reference compatibility table (FB Marketing API v21):
 *   OUTCOME_SALES        + OFFSITE_CONVERSIONS / VALUE / LANDING_PAGE_VIEWS
 *   OUTCOME_LEADS        + LEAD_GENERATION / OFFSITE_CONVERSIONS / QUALITY_LEAD
 *   OUTCOME_TRAFFIC      + LINK_CLICKS / LANDING_PAGE_VIEWS / REACH / IMPRESSIONS
 *   OUTCOME_ENGAGEMENT   + POST_ENGAGEMENT / PAGE_LIKES / EVENT_RESPONSES
 *   OUTCOME_AWARENESS    + REACH / IMPRESSIONS / AD_RECALL_LIFT / THRUPLAY
 *   OUTCOME_APP_PROMOTION+ APP_INSTALLS / OFFSITE_CONVERSIONS
 */
type PresetId =
  | "sales"
  | "leads"
  | "traffic"
  | "engagement"
  | "awareness"
  | "app_installs"
  | "video_views"
  | "custom";

interface Preset {
  id: PresetId;
  emoji: string;
  label: string;
  hint: string;
  objective: string;
  optimization_goal: string;
  billing_event: string;
  needs_pixel: boolean;
  default_event_type: string | null;
}

const PRESETS: Preset[] = [
  {
    id: "sales",
    emoji: "🛒",
    label: "Sales (Purchases)",
    hint: "Sales campaigns optimised on Pixel purchases. Most common.",
    objective: "OUTCOME_SALES",
    optimization_goal: "OFFSITE_CONVERSIONS",
    billing_event: "IMPRESSIONS",
    needs_pixel: true,
    default_event_type: "PURCHASE",
  },
  {
    id: "leads",
    emoji: "📥",
    label: "Leads",
    hint: "On-site lead form conversions tracked via Pixel.",
    objective: "OUTCOME_LEADS",
    optimization_goal: "OFFSITE_CONVERSIONS",
    billing_event: "IMPRESSIONS",
    needs_pixel: true,
    default_event_type: "LEAD",
  },
  {
    id: "traffic",
    emoji: "🔗",
    label: "Traffic (Link clicks)",
    hint: "Just send people to your URL. No pixel needed.",
    objective: "OUTCOME_TRAFFIC",
    optimization_goal: "LINK_CLICKS",
    billing_event: "IMPRESSIONS",
    needs_pixel: false,
    default_event_type: null,
  },
  {
    id: "engagement",
    emoji: "❤️",
    label: "Engagement",
    hint: "Likes / reactions / comments / shares.",
    objective: "OUTCOME_ENGAGEMENT",
    optimization_goal: "POST_ENGAGEMENT",
    billing_event: "IMPRESSIONS",
    needs_pixel: false,
    default_event_type: null,
  },
  {
    id: "awareness",
    emoji: "📢",
    label: "Awareness (Reach)",
    hint: "Maximise unique impressions in the audience.",
    objective: "OUTCOME_AWARENESS",
    optimization_goal: "REACH",
    billing_event: "IMPRESSIONS",
    needs_pixel: false,
    default_event_type: null,
  },
  {
    id: "video_views",
    emoji: "▶️",
    label: "Video views",
    hint: "Optimise for ThruPlays (15s+).",
    objective: "OUTCOME_AWARENESS",
    optimization_goal: "THRUPLAY",
    billing_event: "IMPRESSIONS",
    needs_pixel: false,
    default_event_type: null,
  },
  {
    id: "app_installs",
    emoji: "📱",
    label: "App installs",
    hint: "Drive app installs (requires app_id + store_url).",
    objective: "OUTCOME_APP_PROMOTION",
    optimization_goal: "APP_INSTALLS",
    billing_event: "IMPRESSIONS",
    needs_pixel: false,
    default_event_type: null,
  },
];

/**
 * Compatibility map: objective -> set of optimization_goals FB accepts.
 * Used to flag misconfigured templates BEFORE we hit the FB API.
 * Conservative — extra valid combos aren't blocking, we only warn.
 */
const COMPATIBLE_GOALS: Record<string, string[]> = {
  OUTCOME_SALES: [
    "OFFSITE_CONVERSIONS",
    "VALUE",
    "LANDING_PAGE_VIEWS",
    "LINK_CLICKS",
  ],
  OUTCOME_LEADS: [
    "LEAD_GENERATION",
    "OFFSITE_CONVERSIONS",
    "QUALITY_LEAD",
    "LANDING_PAGE_VIEWS",
    "LINK_CLICKS",
  ],
  OUTCOME_TRAFFIC: [
    "LINK_CLICKS",
    "LANDING_PAGE_VIEWS",
    "REACH",
    "IMPRESSIONS",
  ],
  OUTCOME_ENGAGEMENT: [
    "POST_ENGAGEMENT",
    "PAGE_LIKES",
    "EVENT_RESPONSES",
    "REACH",
    "IMPRESSIONS",
    "THRUPLAY",
  ],
  OUTCOME_AWARENESS: [
    "REACH",
    "IMPRESSIONS",
    "AD_RECALL_LIFT",
    "THRUPLAY",
  ],
  OUTCOME_APP_PROMOTION: ["APP_INSTALLS", "OFFSITE_CONVERSIONS", "LINK_CLICKS"],
};

function isCompatible(objective: string, optimization_goal: string): boolean {
  const allowed = COMPATIBLE_GOALS[objective];
  if (!allowed) return true; // unknown objective — don't block
  return allowed.includes(optimization_goal);
}

function detectPresetId(cfg: TemplateConfig): PresetId {
  for (const p of PRESETS) {
    if (
      p.objective === cfg.campaign.objective &&
      p.optimization_goal === cfg.adset.optimization_goal
    ) {
      return p.id;
    }
  }
  return "custom";
}

function applyPreset(cfg: TemplateConfig, preset: Preset): TemplateConfig {
  const next = {
    campaign: {
      ...cfg.campaign,
      objective: preset.objective,
    },
    adset: {
      ...cfg.adset,
      optimization_goal: preset.optimization_goal,
      billing_event: preset.billing_event,
    },
  };
  if (preset.needs_pixel) {
    const existing = cfg.adset.promoted_object ?? {};
    next.adset.promoted_object = {
      ...existing,
      custom_event_type:
        existing.custom_event_type || preset.default_event_type,
    };
  }
  return next;
}

function defaultConfig(): TemplateConfig {
  return {
    campaign: {
      objective: "OUTCOME_SALES",
      status: "PAUSED",
      special_ad_categories: [],
      buying_type: "AUCTION",
      daily_budget: 50,
      lifetime_budget: null,
      bid_strategy: "LOWEST_COST_WITHOUT_CAP",
    },
    adset: {
      optimization_goal: "OFFSITE_CONVERSIONS",
      billing_event: "IMPRESSIONS",
      status: "PAUSED",
      daily_budget: null,
      lifetime_budget: null,
      bid_amount: null,
      targeting: {
        countries: ["PL"],
        age_min: 18,
        age_max: 65,
        genders: [],
        locales: [],
        publisher_platforms: [],
      },
      promoted_object: null,
      destination_type: null,
      start_time: null,
      end_time: null,
      dsa_beneficiary: null,
      dsa_payor: null,
    },
  };
}

// ---------------------------------------------------------------- main page

type Step = "template" | "accounts" | "review";

export function Autozaliv() {
  const [step, setStep] = useState<Step>("template");
  const [selectedTemplateId, setSelectedTemplateId] = useState<number | null>(null);
  const [selectedAccounts, setSelectedAccounts] = useState<Set<string>>(new Set());
  // selectedAccounts keys are `${token_id}:${account_id}` so we keep the pair.

  return (
    <Layout
      title="Autozaliv"
      description="Launch Campaigns + AdSets across multiple ad accounts in one go"
    >
      <Stepper step={step} />
      {step === "template" && (
        <TemplateStep
          selectedId={selectedTemplateId}
          onSelect={(id) => {
            setSelectedTemplateId(id);
            setStep("accounts");
          }}
        />
      )}
      {step === "accounts" && selectedTemplateId !== null && (
        <AccountsStep
          selected={selectedAccounts}
          setSelected={setSelectedAccounts}
          onBack={() => setStep("template")}
          onNext={() => setStep("review")}
        />
      )}
      {step === "review" && selectedTemplateId !== null && (
        <ReviewStep
          templateId={selectedTemplateId}
          selected={selectedAccounts}
          onBack={() => setStep("accounts")}
        />
      )}
    </Layout>
  );
}

// ---------------------------------------------------------------- stepper

function Stepper({ step }: { step: Step }) {
  const items: { id: Step; label: string }[] = [
    { id: "template", label: "1. Template" },
    { id: "accounts", label: "2. Accounts" },
    { id: "review", label: "3. Review & launch" },
  ];
  const activeIdx = items.findIndex((i) => i.id === step);
  return (
    <div className="mb-6 flex items-center gap-2 text-sm">
      {items.map((it, i) => (
        <div key={it.id} className="flex items-center gap-2">
          <span
            className={cn(
              "rounded-full px-3 py-1 font-medium",
              i === activeIdx
                ? "bg-accent text-white"
                : i < activeIdx
                  ? "bg-emerald-100 text-emerald-700"
                  : "bg-ink-100 text-ink-600 dark:bg-ink-800 dark:text-ink-400",
            )}
          >
            {it.label}
          </span>
          {i < items.length - 1 && <ArrowRight className="h-3 w-3 text-ink-400" />}
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------- step 1: templates

function TemplateStep({
  selectedId,
  onSelect,
}: {
  selectedId: number | null;
  onSelect: (id: number) => void;
}) {
  const qc = useQueryClient();
  const [editing, setEditing] = useState<Template | "new" | null>(null);

  const tplQuery = useQuery({
    queryKey: ["launch-templates"],
    queryFn: async (): Promise<Template[]> => {
      const r = await api.get("/launch/templates");
      return r.data;
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async (id: number) => api.delete(`/launch/templates/${id}`),
    onSuccess: () => {
      toast.success("Template deleted");
      void qc.invalidateQueries({ queryKey: ["launch-templates"] });
    },
    onError: (err) => toast.error(getApiErrorMessage(err)),
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-ink-500">
          Pick a saved template or create a new one. Templates store campaign + adset
          settings; later you'll point them at any number of ad accounts.
        </p>
        <Button onClick={() => setEditing("new")}>
          <Plus className="h-4 w-4" />
          New template
        </Button>
      </div>

      {tplQuery.isLoading && (
        <div className="flex h-40 items-center justify-center text-ink-400">
          <Loader2 className="h-5 w-5 animate-spin" />
        </div>
      )}

      {tplQuery.data && tplQuery.data.length === 0 && (
        <Card>
          <CardBody className="flex flex-col items-center gap-3 py-12 text-center">
            <FileText className="h-8 w-8 text-ink-300" />
            <div className="text-sm font-medium">No templates yet</div>
            <div className="max-w-md text-xs text-ink-500">
              Templates capture all the campaign + adset parameters so you can spin up
              identical setups across many accounts in one click.
            </div>
            <Button size="sm" onClick={() => setEditing("new")}>
              Create your first template
            </Button>
          </CardBody>
        </Card>
      )}

      {tplQuery.data && tplQuery.data.length > 0 && (
        <div className="grid gap-3 md:grid-cols-2">
          {tplQuery.data.map((t) => (
            <Card key={t.id}>
              <CardBody className="space-y-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="truncate text-sm font-semibold">{t.name}</div>
                    {t.description && (
                      <div className="mt-1 line-clamp-2 text-xs text-ink-500">
                        {t.description}
                      </div>
                    )}
                  </div>
                  <div className="flex flex-shrink-0 gap-1">
                    <button
                      title="Edit"
                      className="rounded p-1.5 text-ink-500 hover:bg-ink-100 dark:hover:bg-ink-800"
                      onClick={() => setEditing(t)}
                    >
                      <Edit3 className="h-3.5 w-3.5" />
                    </button>
                    <button
                      title="Delete"
                      className="rounded p-1.5 text-ink-500 hover:bg-rose-50 hover:text-rose-600"
                      onClick={() => {
                        if (confirm(`Delete template "${t.name}"?`)) {
                          deleteMutation.mutate(t.id);
                        }
                      }}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>

                <div className="flex flex-wrap gap-1.5 text-[11px]">
                  <Chip>{t.config.campaign.objective}</Chip>
                  <Chip>{t.config.adset.optimization_goal}</Chip>
                  {t.config.campaign.daily_budget !== null && (
                    <Chip>CBO {t.config.campaign.daily_budget}/day</Chip>
                  )}
                  {t.config.adset.daily_budget !== null && (
                    <Chip>adset {t.config.adset.daily_budget}/day</Chip>
                  )}
                  <Chip>
                    {t.config.adset.targeting.countries.join("/") || "no geo"}{" "}
                    {t.config.adset.targeting.age_min}-{t.config.adset.targeting.age_max}
                  </Chip>
                </div>

                <Button
                  size="sm"
                  className="w-full"
                  onClick={() => onSelect(t.id)}
                  variant={selectedId === t.id ? "primary" : "secondary"}
                >
                  Use this template
                </Button>
              </CardBody>
            </Card>
          ))}
        </div>
      )}

      {editing && (
        <TemplateFormModal
          template={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            void qc.invalidateQueries({ queryKey: ["launch-templates"] });
          }}
        />
      )}
    </div>
  );
}

function Chip({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded-md bg-ink-100 px-1.5 py-0.5 font-medium text-ink-700 dark:bg-ink-800 dark:text-ink-300">
      {children}
    </span>
  );
}

// ---------------------------------------------------------------- template form

function TemplateFormModal({
  template,
  onClose,
  onSaved,
}: {
  template: Template | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState(template?.name ?? "");
  const [description, setDescription] = useState(template?.description ?? "");
  const [cfg, setCfg] = useState<TemplateConfig>(template?.config ?? defaultConfig());

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (template) {
        return api.put(`/launch/templates/${template.id}`, {
          name,
          description,
          config: cfg,
        });
      }
      return api.post(`/launch/templates`, { name, description, config: cfg });
    },
    onSuccess: () => {
      toast.success(template ? "Template updated" : "Template created");
      onSaved();
    },
    onError: (err) => toast.error(getApiErrorMessage(err)),
  });

  const setCamp = (patch: Partial<CampaignConfig>) =>
    setCfg((c) => ({ ...c, campaign: { ...c.campaign, ...patch } }));
  const setAds = (patch: Partial<AdSetConfig>) =>
    setCfg((c) => ({ ...c, adset: { ...c.adset, ...patch } }));
  const setTargeting = (patch: Partial<Targeting>) =>
    setCfg((c) => ({
      ...c,
      adset: { ...c.adset, targeting: { ...c.adset.targeting, ...patch } },
    }));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink-900/40 p-4 backdrop-blur-sm">
      <div className="max-h-[90vh] w-full max-w-3xl animate-slide-up overflow-y-auto">
        <Card>
          <CardBody className="relative space-y-5">
            <button
              onClick={onClose}
              className="absolute right-3 top-3 rounded-full p-1 text-ink-400 hover:bg-ink-100"
              aria-label="Close"
            >
              <X className="h-4 w-4" />
            </button>

            <div>
              <h2 className="text-lg font-semibold">
                {template ? "Edit template" : "New template"}
              </h2>
              <p className="mt-1 text-xs text-ink-500">
                Settings here apply to every account at launch time.
              </p>
            </div>

            <div className="grid gap-3 md:grid-cols-2">
              <Input
                label="Name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Sales PL"
              />
              <Input
                label="Description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="optional"
              />
            </div>

            {/* Goal preset (one click = compatible objective + opt goal) */}
            <Section title="Goal preset">
              <p className="-mt-1 mb-2 text-xs text-ink-500">
                Pick what you actually want. We'll auto-fill the right
                <code className="mx-1 rounded bg-ink-100 px-1 py-0.5 dark:bg-ink-800">
                  objective
                </code>
                +
                <code className="mx-1 rounded bg-ink-100 px-1 py-0.5 dark:bg-ink-800">
                  optimization_goal
                </code>
                so FB doesn't reject the combo.
              </p>
              <div className="grid gap-2 sm:grid-cols-2 md:grid-cols-3">
                {PRESETS.map((p) => {
                  const active = detectPresetId(cfg) === p.id;
                  return (
                    <button
                      key={p.id}
                      type="button"
                      onClick={() => setCfg((c) => applyPreset(c, p))}
                      className={cn(
                        "flex flex-col items-start gap-1 rounded-xl border px-3 py-2 text-left text-sm transition-all",
                        active
                          ? "border-accent bg-accent/10 shadow-sm"
                          : "border-ink-200 hover:border-ink-300 hover:bg-ink-50 dark:border-ink-700 dark:hover:bg-ink-800",
                      )}
                    >
                      <span className="font-medium">
                        {p.emoji} {p.label}
                      </span>
                      <span className="text-[11px] leading-tight text-ink-500">
                        {p.hint}
                      </span>
                    </button>
                  );
                })}
              </div>
              {detectPresetId(cfg) === "custom" && (
                <p className="mt-2 text-xs text-amber-600 dark:text-amber-400">
                  ⚠ Custom combination — make sure objective and
                  optimization_goal are compatible (see warning below if any).
                </p>
              )}
            </Section>

            {!isCompatible(
              cfg.campaign.objective,
              cfg.adset.optimization_goal,
            ) && (
              <div className="flex items-start gap-2 rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-700 dark:bg-amber-900/20 dark:text-amber-200">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                <div>
                  <strong>FB will likely reject this combo:</strong>{" "}
                  objective <code>{cfg.campaign.objective}</code> isn't
                  compatible with optimization_goal{" "}
                  <code>{cfg.adset.optimization_goal}</code>. Allowed for{" "}
                  <code>{cfg.campaign.objective}</code>:{" "}
                  <code>
                    {(COMPATIBLE_GOALS[cfg.campaign.objective] ?? []).join(", ")}
                  </code>
                  .
                </div>
              </div>
            )}

            {/* Campaign */}
            <Section title="Campaign">
              <div className="grid gap-3 md:grid-cols-2">
                <Select
                  label="Objective"
                  value={cfg.campaign.objective}
                  options={OBJECTIVES}
                  onChange={(v) => setCamp({ objective: v })}
                />
                <Select
                  label="Status on launch"
                  value={cfg.campaign.status}
                  options={["PAUSED", "ACTIVE"]}
                  onChange={(v) =>
                    setCamp({ status: v as CampaignConfig["status"] })
                  }
                />
                <Input
                  label="Daily budget (campaign-level / CBO)"
                  type="number"
                  value={cfg.campaign.daily_budget ?? ""}
                  onChange={(e) =>
                    setCamp({
                      daily_budget: e.target.value === "" ? null : Number(e.target.value),
                    })
                  }
                  hint="account currency (e.g. PLN). Leave empty for adset-level budget."
                />
                <Select
                  label="Bid strategy"
                  value={cfg.campaign.bid_strategy ?? ""}
                  options={["", ...BID_STRATEGIES]}
                  onChange={(v) => setCamp({ bid_strategy: v || null })}
                />
              </div>
            </Section>

            {/* AdSet */}
            <Section title="Ad set">
              <div className="grid gap-3 md:grid-cols-2">
                <Select
                  label="Optimization goal"
                  value={cfg.adset.optimization_goal}
                  options={OPTIMIZATION_GOALS}
                  onChange={(v) => setAds({ optimization_goal: v })}
                />
                <Select
                  label="Billing event"
                  value={cfg.adset.billing_event}
                  options={BILLING_EVENTS}
                  onChange={(v) => setAds({ billing_event: v })}
                />
                <Input
                  label="Daily budget (adset)"
                  type="number"
                  value={cfg.adset.daily_budget ?? ""}
                  onChange={(e) =>
                    setAds({
                      daily_budget: e.target.value === "" ? null : Number(e.target.value),
                    })
                  }
                  hint="only when CBO is OFF at campaign level"
                />
                <Input
                  label="Bid amount"
                  type="number"
                  value={cfg.adset.bid_amount ?? ""}
                  onChange={(e) =>
                    setAds({
                      bid_amount: e.target.value === "" ? null : Number(e.target.value),
                    })
                  }
                  hint="required for COST_CAP / LOWEST_COST_WITH_BID_CAP"
                />
              </div>
            </Section>

            {/* Targeting */}
            <Section title="Targeting">
              <div className="grid gap-3 md:grid-cols-2">
                <Input
                  label="Countries (ISO codes, comma-separated)"
                  value={cfg.adset.targeting.countries.join(",")}
                  onChange={(e) =>
                    setTargeting({
                      countries: e.target.value
                        .split(",")
                        .map((s) => s.trim().toUpperCase())
                        .filter(Boolean),
                    })
                  }
                  placeholder="PL,UA,DE"
                />
                <div className="grid grid-cols-2 gap-3">
                  <Input
                    label="Age min"
                    type="number"
                    value={cfg.adset.targeting.age_min}
                    onChange={(e) =>
                      setTargeting({ age_min: Number(e.target.value) || 18 })
                    }
                  />
                  <Input
                    label="Age max"
                    type="number"
                    value={cfg.adset.targeting.age_max}
                    onChange={(e) =>
                      setTargeting({ age_max: Number(e.target.value) || 65 })
                    }
                  />
                </div>
                <Select
                  label="Genders"
                  value={
                    cfg.adset.targeting.genders.length === 0
                      ? "all"
                      : cfg.adset.targeting.genders[0] === 1
                        ? "male"
                        : "female"
                  }
                  options={["all", "male", "female"]}
                  onChange={(v) => {
                    if (v === "all") setTargeting({ genders: [] });
                    else if (v === "male") setTargeting({ genders: [1] });
                    else setTargeting({ genders: [2] });
                  }}
                />
              </div>
            </Section>

            {/* Promoted object */}
            <Section title="Promoted object (for SALES / LEADS)">
              <div className="grid gap-3 md:grid-cols-2">
                <Input
                  label="Pixel ID"
                  value={cfg.adset.promoted_object?.pixel_id ?? ""}
                  onChange={(e) =>
                    setAds({
                      promoted_object: {
                        ...(cfg.adset.promoted_object ?? {}),
                        pixel_id: e.target.value || null,
                      },
                    })
                  }
                  placeholder="optional"
                />
                <Select
                  label="Custom event type"
                  value={cfg.adset.promoted_object?.custom_event_type ?? ""}
                  options={["", ...CUSTOM_EVENT_TYPES]}
                  onChange={(v) =>
                    setAds({
                      promoted_object: {
                        ...(cfg.adset.promoted_object ?? {}),
                        custom_event_type: v || null,
                      },
                    })
                  }
                />
              </div>
            </Section>

            {/* DSA */}
            <Section title="EU DSA compliance (required for EU-targeted ads)">
              <div className="grid gap-3 md:grid-cols-2">
                <Input
                  label="DSA beneficiary"
                  value={cfg.adset.dsa_beneficiary ?? ""}
                  onChange={(e) =>
                    setAds({ dsa_beneficiary: e.target.value || null })
                  }
                  placeholder="Person / company being advertised"
                />
                <Input
                  label="DSA payor"
                  value={cfg.adset.dsa_payor ?? ""}
                  onChange={(e) => setAds({ dsa_payor: e.target.value || null })}
                  placeholder="Person / company paying for ads"
                />
              </div>
              <p className="mt-1 text-xs text-ink-500">
                FB rejects EU-targeted adsets without these fields since Feb 2024 (Digital
                Services Act).
              </p>
            </Section>

            <div className="flex items-center justify-end gap-2 border-t border-ink-200/60 pt-4 dark:border-ink-700/60">
              <Button variant="secondary" onClick={onClose}>
                Cancel
              </Button>
              <Button
                onClick={() => saveMutation.mutate()}
                loading={saveMutation.isPending}
                disabled={!name.trim()}
              >
                {template ? "Save changes" : "Create template"}
              </Button>
            </div>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-500">
        {title}
      </div>
      {children}
    </div>
  );
}

function Select({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (v: string) => void;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-ink-700 dark:text-ink-300">
        {label}
      </span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={cn(
          "block w-full rounded-xl border bg-white px-3.5 py-2.5 text-sm",
          "border-ink-200 dark:border-ink-700 dark:bg-ink-800",
          "focus:outline-none focus:ring-2 focus:ring-accent/30 focus:border-accent",
        )}
      >
        {options.map((o) => (
          <option key={o} value={o}>
            {o || "—"}
          </option>
        ))}
      </select>
    </label>
  );
}

// ---------------------------------------------------------------- step 2: accounts

function AccountsStep({
  selected,
  setSelected,
  onBack,
  onNext,
}: {
  selected: Set<string>;
  setSelected: (s: Set<string>) => void;
  onBack: () => void;
  onNext: () => void;
}) {
  const accountsQuery = useQuery({
    queryKey: ["fb-accounts"],
    queryFn: async (): Promise<{ count: number; accounts: AdAccount[] }> => {
      const r = await api.get("/fb-accounts/");
      return r.data;
    },
  });

  const all = accountsQuery.data?.accounts ?? [];
  const keyOf = (a: AdAccount) => `${a.token_id}:${a.id}`;

  const toggle = (a: AdAccount) => {
    const k = keyOf(a);
    const next = new Set(selected);
    if (next.has(k)) next.delete(k);
    else next.add(k);
    setSelected(next);
  };

  const allSelected = all.length > 0 && all.every((a) => selected.has(keyOf(a)));

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-ink-500">
          Pick which ad accounts to launch on. The same Campaign + AdSet will be created
          on each one.
        </p>
        <Button
          size="sm"
          variant="secondary"
          onClick={() => {
            if (allSelected) setSelected(new Set());
            else setSelected(new Set(all.map(keyOf)));
          }}
        >
          {allSelected ? "Clear" : "Select all"}
        </Button>
      </div>

      {accountsQuery.isLoading && (
        <div className="flex h-40 items-center justify-center text-ink-400">
          <Loader2 className="h-5 w-5 animate-spin" />
        </div>
      )}

      {all.length === 0 && !accountsQuery.isLoading && (
        <Card>
          <CardBody className="py-8 text-center text-sm text-ink-500">
            No ad accounts found. Add a token under{" "}
            <a href="/tokens" className="text-accent hover:underline">
              FB Accounts
            </a>{" "}
            first.
          </CardBody>
        </Card>
      )}

      {all.length > 0 && (
        <div className="grid gap-2 md:grid-cols-2">
          {all.map((a) => {
            const k = keyOf(a);
            const isSel = selected.has(k);
            return (
              <button
                key={k}
                onClick={() => toggle(a)}
                className={cn(
                  "flex items-start gap-3 rounded-xl border p-3 text-left transition-colors",
                  isSel
                    ? "border-accent bg-accent/5"
                    : "border-ink-200 bg-white hover:bg-ink-50 dark:border-ink-700 dark:bg-ink-800",
                )}
              >
                <input
                  type="checkbox"
                  checked={isSel}
                  onChange={() => toggle(a)}
                  className="mt-0.5"
                  onClick={(e) => e.stopPropagation()}
                />
                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline justify-between gap-2">
                    <div className="truncate text-sm font-medium">
                      {a.name || `act_${a.id}`}
                    </div>
                    <div className="flex-shrink-0 text-[11px] text-ink-500">
                      {a.currency}
                    </div>
                  </div>
                  <div className="mt-0.5 truncate text-xs text-ink-500">
                    act_{a.id} · {a.fb_user_name ?? a.token_label ?? "—"}
                  </div>
                  {(a.timezone_name || a.amount_spent) && (
                    <div className="mt-0.5 truncate text-[11px] text-ink-400">
                      {a.timezone_name}
                      {a.amount_spent && ` · spent ${a.amount_spent}`}
                    </div>
                  )}
                </div>
              </button>
            );
          })}
        </div>
      )}

      <div className="flex items-center justify-between border-t border-ink-200/60 pt-4 dark:border-ink-700/60">
        <Button variant="secondary" onClick={onBack}>
          <ArrowLeft className="h-4 w-4" />
          Back
        </Button>
        <Button onClick={onNext} disabled={selected.size === 0}>
          {selected.size > 0
            ? `Continue with ${selected.size} account${selected.size > 1 ? "s" : ""}`
            : "Pick at least one account"}
          <ArrowRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- step 3: review

function ReviewStep({
  templateId,
  selected,
  onBack,
}: {
  templateId: number;
  selected: Set<string>;
  onBack: () => void;
}) {
  const targets = useMemo(
    () =>
      Array.from(selected).map((k) => {
        const [token_id, account_id] = k.split(":");
        return { token_id: Number(token_id), account_id };
      }),
    [selected],
  );

  const previewQuery = useQuery({
    queryKey: ["launch-preview", templateId, targets],
    queryFn: async (): Promise<PreviewResponse> => {
      const r = await api.post("/launch/preview", { template_id: templateId, targets });
      return r.data;
    },
  });

  const [launchResult, setLaunchResult] = useState<LaunchResponse | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);

  const launchMutation = useMutation({
    mutationFn: async (): Promise<LaunchResponse> => {
      const r = await api.post("/launch/execute", {
        template_id: templateId,
        targets,
      });
      return r.data;
    },
    onSuccess: (data) => {
      setLaunchResult(data);
      setConfirmOpen(false);
      const ok = data.results.filter((r) => r.ok).length;
      const fail = data.results.length - ok;
      if (fail === 0) toast.success(`Launched ${ok} successfully`);
      else if (ok === 0) toast.error(`All ${fail} launches failed`);
      else toast(`Launched ${ok} ok, ${fail} failed`);
    },
    onError: (err) => toast.error(getApiErrorMessage(err)),
  });

  return (
    <div className="space-y-4">
      <p className="text-sm text-ink-500">
        Review what will be created. Nothing is sent to Facebook until you click{" "}
        <strong>Launch</strong>.
      </p>

      {previewQuery.isLoading && (
        <div className="flex h-40 items-center justify-center text-ink-400">
          <Loader2 className="h-5 w-5 animate-spin" />
        </div>
      )}

      {previewQuery.data && previewQuery.data.warnings.length > 0 && (
        <div className="rounded-xl border border-amber-300/50 bg-amber-50 p-3 text-xs dark:border-amber-700/50 dark:bg-amber-900/20">
          <div className="flex items-center gap-2 font-medium text-amber-700 dark:text-amber-300">
            <AlertTriangle className="h-3.5 w-3.5" />
            {previewQuery.data.warnings.length} warning(s)
          </div>
          <ul className="mt-1 list-disc pl-5 text-amber-700 dark:text-amber-300">
            {previewQuery.data.warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      {previewQuery.data && (
        <Card>
          <CardBody className="overflow-x-auto p-0">
            <table className="w-full text-xs">
              <thead className="bg-ink-50 text-ink-600 dark:bg-ink-800/40">
                <tr>
                  <th className="px-3 py-2 text-left font-medium">Account</th>
                  <th className="px-3 py-2 text-left font-medium">Campaign name</th>
                  <th className="px-3 py-2 text-left font-medium">Objective</th>
                  <th className="px-3 py-2 text-left font-medium">Budget</th>
                  <th className="px-3 py-2 text-left font-medium">Optimization</th>
                  <th className="px-3 py-2 text-left font-medium">Targeting</th>
                </tr>
              </thead>
              <tbody>
                {previewQuery.data.plan.map((row, i) => (
                  <tr
                    key={`${row.token_id}:${row.account_id}:${i}`}
                    className="border-t border-ink-100 dark:border-ink-800"
                  >
                    <td className="px-3 py-2">
                      <div className="font-medium">
                        {row.account_name || `act_${row.account_id}`}
                      </div>
                      <div className="text-[10px] text-ink-500">
                        act_{row.account_id} · {row.currency}
                      </div>
                    </td>
                    <td className="px-3 py-2">{row.campaign_name}</td>
                    <td className="px-3 py-2 text-ink-600">{row.objective}</td>
                    <td className="px-3 py-2 text-ink-600">
                      {row.daily_budget ?? "—"}
                    </td>
                    <td className="px-3 py-2 text-ink-600">{row.optimization_goal}</td>
                    <td className="px-3 py-2 text-ink-600">{row.targeting_summary}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardBody>
        </Card>
      )}

      <div className="flex items-center justify-between border-t border-ink-200/60 pt-4 dark:border-ink-700/60">
        <Button variant="secondary" onClick={onBack}>
          <ArrowLeft className="h-4 w-4" />
          Back
        </Button>
        <Button
          onClick={() => setConfirmOpen(true)}
          disabled={!previewQuery.data || previewQuery.data.plan.length === 0}
        >
          <Rocket className="h-4 w-4" />
          Launch on {targets.length} account{targets.length > 1 ? "s" : ""}
        </Button>
      </div>

      {confirmOpen && (
        <Modal onClose={() => setConfirmOpen(false)}>
          <h2 className="text-base font-semibold">
            Launch {targets.length} campaign(s)?
          </h2>
          <p className="mt-1 text-sm text-ink-500">
            Each account will get a new Campaign + AdSet. Status will be{" "}
            <strong>PAUSED</strong> by default — you can activate them in Bulk Actions
            after review.
          </p>
          <div className="mt-4 flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setConfirmOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={() => launchMutation.mutate()}
              loading={launchMutation.isPending}
            >
              <Rocket className="h-4 w-4" />
              Launch
            </Button>
          </div>
        </Modal>
      )}

      {launchResult && (
        <LaunchResultModal result={launchResult} onClose={() => setLaunchResult(null)} />
      )}
    </div>
  );
}

function LaunchResultModal({
  result,
  onClose,
}: {
  result: LaunchResponse;
  onClose: () => void;
}) {
  const ok = result.results.filter((r) => r.ok);
  const fail = result.results.filter((r) => !r.ok);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink-900/40 p-4 backdrop-blur-sm">
      <div className="max-h-[90vh] w-full max-w-2xl animate-slide-up overflow-y-auto">
        <Card>
          <CardBody className="relative space-y-3">
            <button
              onClick={onClose}
              className="absolute right-3 top-3 rounded-full p-1 text-ink-400 hover:bg-ink-100"
              aria-label="Close"
            >
              <X className="h-4 w-4" />
            </button>
            <h2 className="text-lg font-semibold">Launch result</h2>
            <div className="flex gap-4 text-sm">
              <span className="text-emerald-600">
                <CheckCircle2 className="mr-1 inline h-4 w-4" />
                {ok.length} succeeded
              </span>
              {fail.length > 0 && (
                <span className="text-rose-600">
                  <XCircle className="mr-1 inline h-4 w-4" />
                  {fail.length} failed
                </span>
              )}
            </div>

            {ok.length > 0 && (
              <Section title="Succeeded">
                <ul className="space-y-1 text-xs">
                  {ok.map((r, i) => (
                    <li
                      key={i}
                      className="rounded-md bg-emerald-50 px-2 py-1 dark:bg-emerald-900/20"
                    >
                      <span className="font-mono text-emerald-700 dark:text-emerald-300">
                        act_{r.account_id}
                      </span>{" "}
                      → campaign{" "}
                      <code className="text-[11px]">{r.campaign_id}</code>
                      {r.adset_id && (
                        <>
                          {" "}
                          · adset <code className="text-[11px]">{r.adset_id}</code>
                        </>
                      )}
                    </li>
                  ))}
                </ul>
              </Section>
            )}

            {fail.length > 0 && (
              <Section title="Failed">
                <ul className="space-y-1 text-xs">
                  {fail.map((r, i) => (
                    <li
                      key={i}
                      className="rounded-md bg-rose-50 px-2 py-1 dark:bg-rose-900/20"
                    >
                      <span className="font-mono text-rose-700 dark:text-rose-300">
                        act_{r.account_id}
                      </span>{" "}
                      — {r.error}
                    </li>
                  ))}
                </ul>
              </Section>
            )}

            <div className="flex justify-end pt-2">
              <Button variant="secondary" onClick={onClose}>
                Close
              </Button>
            </div>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}

function Modal({
  children,
  onClose,
}: {
  children: React.ReactNode;
  onClose: () => void;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink-900/40 p-4 backdrop-blur-sm">
      <div className="w-full max-w-md animate-slide-up">
        <Card>
          <CardBody className="relative">
            <button
              onClick={onClose}
              className="absolute right-3 top-3 rounded-full p-1 text-ink-400 hover:bg-ink-100"
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

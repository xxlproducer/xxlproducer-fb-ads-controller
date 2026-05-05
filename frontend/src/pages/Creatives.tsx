import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  Image as ImageIcon,
  Loader2,
  Pencil,
  Plus,
  Rocket,
  Trash2,
  Upload,
  Video,
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

interface Creative {
  id: number;
  name: string;
  media_type: "image" | "video";
  media_filename: string;
  media_mime: string | null;
  thumbnail_filename: string | null;
  title: string | null;
  body: string | null;
  description: string | null;
  link_url: string | null;
  cta_type: string | null;
  page_id: string | null;
  instagram_actor_id: string | null;
  created_at: string;
  updated_at: string;
}

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
}

interface AdResult {
  token_id: number;
  ad_account_id: string;
  adset_id: string;
  success: boolean;
  ad_id: string | null;
  creative_id_fb: string | null;
  image_hash: string | null;
  video_id: string | null;
  error: string | null;
}

interface BulkCreateAdsResponse {
  total: number;
  succeeded: number;
  failed: number;
  results: AdResult[];
}

const CTA_OPTIONS = [
  "LEARN_MORE",
  "SHOP_NOW",
  "SIGN_UP",
  "DOWNLOAD",
  "GET_OFFER",
  "BOOK_TRAVEL",
  "SUBSCRIBE",
  "WATCH_MORE",
  "CONTACT_US",
  "APPLY_NOW",
  "GET_QUOTE",
  "ORDER_NOW",
  "PLAY_GAME",
  "INSTALL_MOBILE_APP",
];

// ---------------------------------------------------------------- page

export function Creatives() {
  const qc = useQueryClient();
  const [editing, setEditing] = useState<Creative | "new" | null>(null);
  const [launching, setLaunching] = useState<Creative | null>(null);

  const list = useQuery({
    queryKey: ["creatives"],
    queryFn: async () => {
      const { data } = await api.get<Creative[]>("/creatives");
      return data;
    },
  });

  const del = useMutation({
    mutationFn: async (id: number) => {
      await api.delete(`/creatives/${id}`);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["creatives"] });
      toast.success("Creative deleted");
    },
    onError: (e) => toast.error(getApiErrorMessage(e)),
  });

  return (
    <Layout
      title="Creatives"
      description="Reusable image / video creatives. Upload once, deploy across many ad accounts at once."
      actions={
        <Button onClick={() => setEditing("new")}>
          <Plus className="mr-1 h-4 w-4" /> New creative
        </Button>
      }
    >
      <div className="mx-auto max-w-7xl space-y-6 px-6 py-8">

        {list.isLoading ? (
          <div className="flex items-center gap-2 text-ink-500">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading...
          </div>
        ) : list.data && list.data.length > 0 ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {list.data.map((c) => (
              <CreativeCard
                key={c.id}
                c={c}
                onEdit={() => setEditing(c)}
                onDelete={() => del.mutate(c.id)}
                onLaunch={() => setLaunching(c)}
              />
            ))}
          </div>
        ) : (
          <Card>
            <CardBody className="py-16 text-center">
              <ImageIcon className="mx-auto h-12 w-12 text-ink-300" />
              <p className="mt-3 text-sm text-ink-500">
                No creatives yet. Click <strong>New creative</strong> to upload
                your first image or video.
              </p>
            </CardBody>
          </Card>
        )}
      </div>

      {editing && (
        <CreativeFormModal
          creative={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            qc.invalidateQueries({ queryKey: ["creatives"] });
            setEditing(null);
          }}
        />
      )}

      {launching && (
        <LaunchAdsModal
          creative={launching}
          onClose={() => setLaunching(null)}
        />
      )}
    </Layout>
  );
}

// ---------------------------------------------------------------- card

function CreativeCard({
  c,
  onEdit,
  onDelete,
  onLaunch,
}: {
  c: Creative;
  onEdit: () => void;
  onDelete: () => void;
  onLaunch: () => void;
}) {
  const isVideo = c.media_type === "video";
  return (
    <Card>
      <div className="aspect-video overflow-hidden rounded-t-2xl bg-ink-100 dark:bg-ink-800">
        {isVideo ? (
          <div className="flex h-full items-center justify-center">
            <Video className="h-12 w-12 text-ink-400" />
          </div>
        ) : (
          <img
            src={`/api/creatives/${c.id}/media`}
            alt={c.name}
            className="h-full w-full object-cover"
          />
        )}
      </div>
      <CardBody className="space-y-2">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-semibold tracking-tight">
              {c.name}
            </div>
            {c.title && (
              <div className="truncate text-xs text-ink-600 dark:text-ink-400">
                {c.title}
              </div>
            )}
          </div>
          <span className="shrink-0 rounded-full bg-ink-100 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-ink-600 dark:bg-ink-800 dark:text-ink-300">
            {c.media_type}
          </span>
        </div>
        {c.body && (
          <p className="line-clamp-2 text-xs text-ink-500">{c.body}</p>
        )}
        {c.link_url && (
          <a
            href={c.link_url}
            target="_blank"
            rel="noreferrer"
            className="block truncate text-xs text-blue-600 hover:underline dark:text-blue-400"
          >
            {c.link_url}
          </a>
        )}
        <div className="flex items-center gap-2 pt-2">
          <Button onClick={onLaunch} size="sm" className="flex-1">
            <Rocket className="mr-1 h-3.5 w-3.5" />
            Launch Ads
          </Button>
          <Button onClick={onEdit} variant="secondary" size="sm">
            <Pencil className="h-3.5 w-3.5" />
          </Button>
          <Button onClick={onDelete} variant="ghost" size="sm">
            <Trash2 className="h-3.5 w-3.5 text-red-500" />
          </Button>
        </div>
      </CardBody>
    </Card>
  );
}

// ---------------------------------------------------------------- create / edit modal

function CreativeFormModal({
  creative,
  onClose,
  onSaved,
}: {
  creative: Creative | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const isEdit = !!creative;
  const [name, setName] = useState(creative?.name ?? "");
  const [title, setTitle] = useState(creative?.title ?? "");
  const [body, setBody] = useState(creative?.body ?? "");
  const [description, setDescription] = useState(creative?.description ?? "");
  const [linkUrl, setLinkUrl] = useState(creative?.link_url ?? "");
  const [ctaType, setCtaType] = useState(creative?.cta_type ?? "LEARN_MORE");
  const [pageId, setPageId] = useState(creative?.page_id ?? "");
  const [instagramActorId, setInstagramActorId] = useState(
    creative?.instagram_actor_id ?? "",
  );
  const [file, setFile] = useState<File | null>(null);

  const save = useMutation({
    mutationFn: async () => {
      if (isEdit && creative) {
        const { data } = await api.patch<Creative>(`/creatives/${creative.id}`, {
          name,
          title: title || null,
          body: body || null,
          description: description || null,
          link_url: linkUrl || null,
          cta_type: ctaType || null,
          page_id: pageId || null,
          instagram_actor_id: instagramActorId || null,
        });
        return data;
      }
      if (!file) throw new Error("Please select a media file (image or video)");
      const fd = new FormData();
      fd.append("name", name);
      fd.append("media", file);
      if (title) fd.append("title", title);
      if (body) fd.append("body", body);
      if (description) fd.append("description", description);
      if (linkUrl) fd.append("link_url", linkUrl);
      if (ctaType) fd.append("cta_type", ctaType);
      if (pageId) fd.append("page_id", pageId);
      if (instagramActorId) fd.append("instagram_actor_id", instagramActorId);
      const { data } = await api.post<Creative>("/creatives", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      return data;
    },
    onSuccess: () => {
      toast.success(isEdit ? "Creative updated" : "Creative created");
      onSaved();
    },
    onError: (e) => toast.error(getApiErrorMessage(e)),
  });

  return (
    <ModalShell
      title={isEdit ? "Edit creative" : "New creative"}
      onClose={onClose}
    >
      <div className="space-y-4">
        {!isEdit && (
          <div>
            <label className="mb-1 block text-xs font-medium text-ink-600 dark:text-ink-400">
              Media file (image or video)
            </label>
            <label
              className={cn(
                "flex cursor-pointer items-center gap-2 rounded-xl border border-dashed border-ink-300 bg-ink-50 p-4 text-sm",
                "hover:border-ink-400 hover:bg-ink-100 dark:border-ink-700 dark:bg-ink-900 dark:hover:border-ink-600",
              )}
            >
              <Upload className="h-4 w-4 text-ink-500" />
              <span className="truncate text-ink-700 dark:text-ink-300">
                {file ? file.name : "Select image or video..."}
              </span>
              <input
                type="file"
                accept="image/jpeg,image/png,image/gif,image/webp,video/mp4,video/quicktime"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                className="hidden"
              />
            </label>
          </div>
        )}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="Name *">
            <Input value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <Field label="CTA">
            <select
              value={ctaType}
              onChange={(e) => setCtaType(e.target.value)}
              className="h-9 w-full rounded-xl border border-ink-200 bg-white px-3 text-sm dark:border-ink-700 dark:bg-ink-900"
            >
              {CTA_OPTIONS.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </Field>
        </div>
        <Field label="Title (headline)">
          <Input value={title} onChange={(e) => setTitle(e.target.value)} />
        </Field>
        <Field label="Primary text (body)">
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            rows={3}
            className="w-full rounded-xl border border-ink-200 bg-white px-3 py-2 text-sm dark:border-ink-700 dark:bg-ink-900"
          />
        </Field>
        <Field label="Description">
          <Input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </Field>
        <Field label="Link URL">
          <Input
            value={linkUrl}
            onChange={(e) => setLinkUrl(e.target.value)}
            placeholder="https://example.com/landing"
          />
        </Field>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="FB Page ID *">
            <Input
              value={pageId}
              onChange={(e) => setPageId(e.target.value)}
              placeholder="e.g. 1234567890"
            />
          </Field>
          <Field label="Instagram Actor ID (optional)">
            <Input
              value={instagramActorId}
              onChange={(e) => setInstagramActorId(e.target.value)}
            />
          </Field>
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            onClick={() => save.mutate()}
            disabled={save.isPending || !name || (!isEdit && !file)}
          >
            {save.isPending && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
            {isEdit ? "Save" : "Create"}
          </Button>
        </div>
      </div>
    </ModalShell>
  );
}

// ---------------------------------------------------------------- launch ads modal

function LaunchAdsModal({
  creative,
  onClose,
}: {
  creative: Creative;
  onClose: () => void;
}) {
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [status, setStatus] = useState<"PAUSED" | "ACTIVE">("PAUSED");
  const [results, setResults] = useState<BulkCreateAdsResponse | null>(null);

  const inv = useQuery({
    queryKey: ["bulk-inventory", "adset"],
    queryFn: async () => {
      const { data } = await api.post<InventoryResponse>("/bulk/inventory", {
        level: "adset",
      });
      return data;
    },
  });

  const filtered = useMemo(() => {
    const rows = inv.data?.rows ?? [];
    const q = search.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter(
      (r) =>
        r.name?.toLowerCase().includes(q) ||
        r.object_id.includes(q) ||
        r.account_id.includes(q),
    );
  }, [inv.data, search]);

  const keyOf = (r: InventoryRow) => `${r.token_id}:${r.object_id}`;

  const toggle = (r: InventoryRow) => {
    const k = keyOf(r);
    const next = new Set(selected);
    if (next.has(k)) next.delete(k);
    else next.add(k);
    setSelected(next);
  };

  const toggleAll = (checked: boolean) => {
    if (!checked) {
      setSelected(new Set());
      return;
    }
    setSelected(new Set(filtered.map(keyOf)));
  };

  const launch = useMutation({
    mutationFn: async () => {
      const sel = filtered.filter((r) => selected.has(keyOf(r)));
      const targets = sel.map((r) => ({
        token_id: r.token_id,
        ad_account_id: r.account_id,
        adset_id: r.object_id,
      }));
      const { data } = await api.post<BulkCreateAdsResponse>(
        "/creatives/bulk_create_ads",
        { creative_id: creative.id, targets, status },
      );
      return data;
    },
    onSuccess: (data) => {
      setResults(data);
      if (data.failed === 0) {
        toast.success(`Created ${data.succeeded} ads`);
      } else {
        toast.error(`${data.succeeded} succeeded, ${data.failed} failed`);
      }
    },
    onError: (e) => toast.error(getApiErrorMessage(e)),
  });

  if (results) {
    return (
      <ModalShell title="Launch results" onClose={onClose} wide>
        <div className="space-y-3">
          <div className="flex items-center gap-3 text-sm">
            <span className="rounded-lg bg-green-100 px-2 py-1 font-medium text-green-700 dark:bg-green-900/30 dark:text-green-300">
              {results.succeeded} succeeded
            </span>
            {results.failed > 0 && (
              <span className="rounded-lg bg-red-100 px-2 py-1 font-medium text-red-700 dark:bg-red-900/30 dark:text-red-300">
                {results.failed} failed
              </span>
            )}
          </div>
          <div className="max-h-96 overflow-y-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="border-b border-ink-200 text-left text-xs uppercase tracking-wide text-ink-500 dark:border-ink-700">
                  <th className="px-2 py-2">Status</th>
                  <th className="px-2 py-2">Account</th>
                  <th className="px-2 py-2">Adset</th>
                  <th className="px-2 py-2">Ad ID</th>
                  <th className="px-2 py-2">Error</th>
                </tr>
              </thead>
              <tbody>
                {results.results.map((r, i) => (
                  <tr
                    key={i}
                    className="border-b border-ink-100 dark:border-ink-800"
                  >
                    <td className="px-2 py-2">
                      {r.success ? (
                        <CheckCircle2 className="h-4 w-4 text-green-600" />
                      ) : (
                        <XCircle className="h-4 w-4 text-red-500" />
                      )}
                    </td>
                    <td className="px-2 py-2 font-mono text-xs">
                      {r.ad_account_id}
                    </td>
                    <td className="px-2 py-2 font-mono text-xs">
                      {r.adset_id}
                    </td>
                    <td className="px-2 py-2 font-mono text-xs">
                      {r.ad_id ?? "—"}
                    </td>
                    <td className="px-2 py-2 text-xs text-red-600 dark:text-red-400">
                      {r.error ?? ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button onClick={onClose}>Close</Button>
          </div>
        </div>
      </ModalShell>
    );
  }

  const errors =
    !creative.page_id || !creative.link_url
      ? "Creative is missing page_id or link_url. Edit it before launching."
      : null;

  return (
    <ModalShell title={`Launch ads — ${creative.name}`} onClose={onClose} wide>
      <div className="space-y-3">
        {errors && (
          <div className="flex items-start gap-2 rounded-xl bg-amber-50 p-3 text-sm text-amber-800 dark:bg-amber-900/20 dark:text-amber-300">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{errors}</span>
          </div>
        )}
        <div className="flex items-center gap-3">
          <Input
            placeholder="Search adsets by name / id / account..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="flex-1"
          />
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value as "PAUSED" | "ACTIVE")}
            className="h-9 rounded-xl border border-ink-200 bg-white px-3 text-sm dark:border-ink-700 dark:bg-ink-900"
          >
            <option value="PAUSED">Create paused</option>
            <option value="ACTIVE">Create active</option>
          </select>
        </div>

        {inv.isLoading ? (
          <div className="flex items-center gap-2 text-ink-500">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading adsets...
          </div>
        ) : filtered.length === 0 ? (
          <Card>
            <CardBody className="py-10 text-center text-sm text-ink-500">
              No adsets found. Create some via Autozaliv first.
            </CardBody>
          </Card>
        ) : (
          <div className="max-h-96 overflow-y-auto rounded-xl border border-ink-200 dark:border-ink-700">
            <table className="min-w-full text-sm">
              <thead className="sticky top-0 bg-white dark:bg-ink-900">
                <tr className="border-b border-ink-200 text-left text-xs uppercase tracking-wide text-ink-500 dark:border-ink-700">
                  <th className="w-10 px-2 py-2">
                    <input
                      type="checkbox"
                      checked={
                        selected.size > 0 && selected.size === filtered.length
                      }
                      onChange={(e) => toggleAll(e.target.checked)}
                    />
                  </th>
                  <th className="px-2 py-2">Adset</th>
                  <th className="px-2 py-2">Account</th>
                  <th className="px-2 py-2">Status</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((r) => {
                  const k = keyOf(r);
                  const isSelected = selected.has(k);
                  return (
                    <tr
                      key={k}
                      onClick={() => toggle(r)}
                      className={cn(
                        "cursor-pointer border-b border-ink-100 hover:bg-ink-50 dark:border-ink-800 dark:hover:bg-ink-800/50",
                        isSelected && "bg-blue-50 dark:bg-blue-900/20",
                      )}
                    >
                      <td className="px-2 py-2">
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => toggle(r)}
                          onClick={(e) => e.stopPropagation()}
                        />
                      </td>
                      <td className="px-2 py-2">
                        <div className="font-medium">{r.name ?? "—"}</div>
                        <div className="font-mono text-xs text-ink-500">
                          {r.object_id}
                        </div>
                      </td>
                      <td className="px-2 py-2 font-mono text-xs">
                        {r.account_id}
                      </td>
                      <td className="px-2 py-2 text-xs">
                        {r.effective_status ?? r.status ?? "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        <div className="flex items-center justify-between pt-2">
          <div className="text-sm text-ink-500">
            {selected.size} adset(s) selected
          </div>
          <div className="flex gap-2">
            <Button variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button
              onClick={() => launch.mutate()}
              disabled={launch.isPending || selected.size === 0 || !!errors}
            >
              {launch.isPending && (
                <Loader2 className="mr-1 h-4 w-4 animate-spin" />
              )}
              <Rocket className="mr-1 h-4 w-4" />
              Launch {selected.size} ad{selected.size === 1 ? "" : "s"}
            </Button>
          </div>
        </div>
      </div>
    </ModalShell>
  );
}

// ---------------------------------------------------------------- helpers

function ModalShell({
  title,
  onClose,
  children,
  wide,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
  wide?: boolean;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onClose}
    >
      <div
        className={cn(
          "max-h-[90vh] w-full overflow-y-auto rounded-2xl bg-white shadow-2xl dark:bg-ink-900",
          wide ? "max-w-4xl" : "max-w-xl",
        )}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-ink-200 px-6 py-4 dark:border-ink-700">
          <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
          <button
            onClick={onClose}
            className="rounded-lg p-1 hover:bg-ink-100 dark:hover:bg-ink-800"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="px-6 py-4">{children}</div>
      </div>
    </div>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="mb-1 block text-xs font-medium text-ink-600 dark:text-ink-400">
        {label}
      </label>
      {children}
    </div>
  );
}

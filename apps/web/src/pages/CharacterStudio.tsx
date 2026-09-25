import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, AdCopyResult, ApprovedSet, Asset, Character, Job, LoraStatus, Product } from "../api";

const THEMES = [
  "portrait",
  "casual_bedroom",
  "lingerie_set",
  "outdoor_day",
  "glamour",
  "mirror_selfie",
  "gym",
];

const PRODUCT_PLACEMENT_OPTIONS = [
  { id: "holding", label: "holding" },
  { id: "beside", label: "beside" },
  { id: "using", label: "using" },
  { id: "featured", label: "featured" },
  { id: "wearing", label: "wearing" },
] as const;

type BriefLine = {
  theme: string;
  count: number;
  outfit: string;
  location: string;
  extra: string;
  pose: string;
  useProduct: boolean;
  productId: string;
  productPlacement: string;
};

const FILTERS = ["all", "pending", "approved", "rejected"] as const;

type FluxKnobs = {
  cfg: number;
  guidance: number;
  steps: number;
  hires_fix: boolean;
  hires_denoise: number;
  detail_lora_name: string;
  detail_lora_strength: number;
  upscale_model_name: string;
  pulid_model_name: string;
  pulid_strength: number;
};

const DEFAULT_FLUX_KNOBS: FluxKnobs = {
  cfg: 1,
  guidance: 2.5,
  steps: 28,
  hires_fix: true,
  hires_denoise: 0.4,
  detail_lora_name: "",
  detail_lora_strength: 0.6,
  upscale_model_name: "",
  pulid_model_name: "",
  pulid_strength: 0.7,
};

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function num(value: unknown, fallback: number): number {
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function readFluxKnobs(character: Character | null): FluxKnobs {
  const params = asRecord(character?.current_version?.pipeline_params);
  const flux = asRecord(params.flux && Object.keys(asRecord(params.flux)).length ? params.flux : params);
  return {
    cfg: num(flux.cfg, DEFAULT_FLUX_KNOBS.cfg),
    guidance: num(flux.guidance, DEFAULT_FLUX_KNOBS.guidance),
    steps: num(flux.steps, DEFAULT_FLUX_KNOBS.steps),
    hires_fix: flux.hires_fix === undefined ? true : Boolean(flux.hires_fix),
    hires_denoise: num(flux.hires_denoise, DEFAULT_FLUX_KNOBS.hires_denoise),
    detail_lora_name: flux.detail_lora_name != null ? String(flux.detail_lora_name) : "",
    detail_lora_strength: num(flux.detail_lora_strength, DEFAULT_FLUX_KNOBS.detail_lora_strength),
    upscale_model_name: flux.upscale_model_name != null ? String(flux.upscale_model_name) : "",
    pulid_model_name: flux.pulid_model_name != null ? String(flux.pulid_model_name) : "",
    pulid_strength: num(flux.pulid_strength, DEFAULT_FLUX_KNOBS.pulid_strength),
  };
}

export default function CharacterStudio() {
  const { id } = useParams();
  const [character, setCharacter] = useState<Character | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [lora, setLora] = useState<LoraStatus | null>(null);
  const [sets, setSets] = useState<ApprovedSet[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [lines, setLines] = useState<BriefLine[]>([
    {
      theme: "casual_bedroom",
      count: 4,
      outfit: "oversized tee",
      location: "",
      extra: "",
      pose: "",
      useProduct: false,
      productId: "",
      productPlacement: "holding",
    },
  ]);
  const [loraPath, setLoraPath] = useState("");
  const [loraStrength, setLoraStrength] = useState(0.85);
  const [trainSteps, setTrainSteps] = useState(1500);
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>("all");
  const [assetSort, setAssetSort] = useState<"newest" | "match">("newest");
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [lightbox, setLightbox] = useState<number | null>(null);
  const [setTitle, setSetTitle] = useState("Approved pack");
  const [exportConfirm, setExportConfirm] = useState(false);
  const [adProductId, setAdProductId] = useState("");
  const [adTheme, setAdTheme] = useState("glamour");
  const [adCopy, setAdCopy] = useState<AdCopyResult | null>(null);
  const [adCaptionEdit, setAdCaptionEdit] = useState("");
  const [captionAssetId, setCaptionAssetId] = useState("");
  const [fluxKnobs, setFluxKnobs] = useState<FluxKnobs>(DEFAULT_FLUX_KNOBS);
  const [fluxDirty, setFluxDirty] = useState(false);

  const refresh = useCallback(async () => {
    if (!id) return;
    const [c, j, a, l, s, p] = await Promise.all([
      api.getCharacter(id),
      api.listJobs(id),
      api.listAssets(id),
      api.loraStatus(id),
      api.listApprovedSets(id),
      api.listProducts(),
    ]);
    setCharacter(c);
    setJobs(j);
    setAssets(a);
    setLora(l);
    setSets(s);
    setProducts(p);
  }, [id]);

  useEffect(() => {
    refresh().catch((e) => setError(e.message));
  }, [refresh]);

  useEffect(() => {
    if (!fluxDirty) setFluxKnobs(readFluxKnobs(character));
  }, [character, fluxDirty]);

  const activeJobs = jobs.filter((j) => j.status === "queued" || j.status === "running");
  useEffect(() => {
    if (!activeJobs.length) return;
    const t = setInterval(() => {
      refresh().catch(() => undefined);
    }, 2000);
    return () => clearInterval(t);
  }, [activeJobs.length, refresh]);

  const visible = useMemo(() => {
    const list = filter === "all" ? assets : assets.filter((a) => a.decision === filter);
    if (assetSort !== "match") return list;
    return [...list].sort((a, b) => (b.consistency_score ?? -1) - (a.consistency_score ?? -1));
  }, [assets, filter, assetSort]);

  useEffect(() => {
    if (lightbox === null) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setLightbox(null);
      if (e.key === "ArrowRight") setLightbox((i) => (i === null ? i : Math.min(visible.length - 1, i + 1)));
      if (e.key === "ArrowLeft") setLightbox((i) => (i === null ? i : Math.max(0, i - 1)));
      const cur = lightbox !== null ? visible[lightbox] : undefined;
      if (!cur || !id) return;
      if (e.key === "a" || e.key === "A") {
        void decide(cur.id, "approved");
      }
      if (e.key === "r" || e.key === "R") {
        void decide(cur.id, "rejected");
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lightbox, visible, id]);

  async function runSeed() {
    if (!id) return;
    setBusy(true);
    setError(null);
    try {
      const job = await api.seedGallery(id, {
        count: 6,
        themes: ["portrait", "glamour", "casual_bedroom"],
      });
      await refresh();
      if (job.status === "failed") {
        setError(job.error_message || "Seed gallery failed");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function runBatch() {
    if (!id) return;
    for (const line of lines) {
      if (line.useProduct && !line.productId) {
        setError("Turn off product reference or pick a product on each enabled line.");
        return;
      }
    }
    setBusy(true);
    setError(null);
    try {
      await api.stillBatch(id, {
        title: lines.map((l) => l.theme).join(" + ") + " batch",
        aspect_ratio: "4:5",
        items: lines.map((l) => ({
          type: "still",
          count: l.count,
          theme: l.theme,
          outfit_hint: l.outfit || undefined,
          pose_hint: l.pose || undefined,
          location_hint: l.location || undefined,
          extra_prompt: l.extra || undefined,
          product_id: l.useProduct && l.productId ? l.productId : undefined,
          product_placement:
            l.useProduct && l.productId ? l.productPlacement || "holding" : undefined,
        })),
      });
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  function patchFlux(partial: Partial<FluxKnobs>) {
    setFluxDirty(true);
    setFluxKnobs((prev) => ({ ...prev, ...partial }));
  }

  async function saveStillQuality() {
    if (!id || !character?.current_version) return;
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      const params = asRecord(character.current_version.pipeline_params);
      const currentFlux = asRecord(
        params.flux && Object.keys(asRecord(params.flux)).length ? params.flux : params
      );
      await api.updateCharacter(id, {
        pipeline_params: {
          ...params,
          flux: {
            ...currentFlux,
            cfg: fluxKnobs.cfg,
            guidance: fluxKnobs.guidance,
            steps: fluxKnobs.steps,
            hires_fix: fluxKnobs.hires_fix,
            hires_denoise: fluxKnobs.hires_denoise,
            detail_lora_name: fluxKnobs.detail_lora_name.trim() || null,
            detail_lora_strength: fluxKnobs.detail_lora_strength,
            upscale_model_name: fluxKnobs.upscale_model_name.trim() || null,
            pulid_model_name: fluxKnobs.pulid_model_name.trim() || null,
            pulid_strength: fluxKnobs.pulid_strength,
          },
        },
      });
      setFluxDirty(false);
      await refresh();
      setInfo("Still quality settings saved on this character version.");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function runAdCopy(fromAssetId?: string) {
    if (!id) return;
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      const res = await api.generateAdCopy(id, {
        product_id: adProductId || undefined,
        theme: adTheme || undefined,
        count: 3,
        asset_id: fromAssetId || captionAssetId || undefined,
      });
      setAdCopy(res);
      setAdCaptionEdit(res.primary);
      setInfo(`Ad copy ready (${res.engine}${res.product_name ? ` · ${res.product_name}` : ""}).`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function saveCaptionToAsset() {
    if (!id || !captionAssetId || !adCaptionEdit.trim()) {
      setError("Select an output still and generate/edit a caption first.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.saveAssetCaption(id, captionAssetId, {
        caption: adCaptionEdit.trim(),
        short: adCopy?.short,
        cta: adCopy?.cta,
        product_id: adProductId || adCopy?.product_id || undefined,
      });
      setInfo("Caption saved on still — reuse this voice across the campaign.");
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function decide(assetId: string, decision: string) {
    await api.setDecision(assetId, decision);
    await refresh();
  }

  async function removeAsset(assetId: string) {
    if (!window.confirm("Permanently delete this image from the library and disk?")) return;
    setBusy(true);
    setError(null);
    try {
      await api.deleteAsset(assetId, true);
      setLightbox(null);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function deleteRejected() {
    if (!id) return;
    const n = assets.filter((a) => a.decision === "rejected").length;
    if (!n) {
      setError("No rejected images to delete.");
      return;
    }
    if (!window.confirm(`Permanently delete ${n} rejected image(s) from the library and disk?`)) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.bulkDeleteAssets(id, { decision: "rejected", delete_files: true });
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function buildDataset() {
    if (!id) return;
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      const res = await api.buildDataset(id, { decision: "approved", min_images: 4 });
      setInfo(
        `Dataset ready: ${res.image_count} images · trigger "${res.trigger_word}" · ${res.dataset_dir}` +
          (res.warning ? ` · ${res.warning}` : "")
      );
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function trainAndRegister() {
    if (!id) return;
    if (approvedCount < 4) {
      setError("Approve at least 4 photoreal stills first.");
      return;
    }
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      const job = await api.trainLora(id, {
        steps: trainSteps,
        strength: loraStrength,
        min_images: 4,
        rebuild_dataset: true,
      });
      setInfo(
        `LoRA train queued (${job.id.slice(0, 8)}…). GPU is exclusive until this finishes, then weights register automatically.`
      );
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function registerLora() {
    if (!id || !loraPath.trim()) {
      setError("Enter the path to the trained .safetensors on nemesis.");
      return;
    }
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      const res = await api.registerLora(id, {
        source_path: loraPath.trim(),
        strength: loraStrength,
        install_to_comfy: true,
      });
      setInfo(res.message);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function makeSet() {
    if (!id) return;
    const ids = Object.entries(selected)
      .filter(([, v]) => v)
      .map(([k]) => k);
    const approvedIds = ids.filter((aid) => assets.find((a) => a.id === aid)?.decision === "approved");
    if (!approvedIds.length) {
      setError("Select one or more approved stills.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const s = await api.createApprovedSet(id, { title: setTitle || "Approved pack", asset_ids: approvedIds });
      setInfo(`Approved set created (${s.item_count} files). Confirm and export below.`);
      setSelected({});
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function doExport(setId: string) {
    if (!exportConfirm) {
      setError("Check the adult/synthetic export confirmation first.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const s = await api.exportApprovedSet(setId, true);
      setInfo(`Export ready: ${s.export_path}`);
      if (s.export_path) {
        window.open(api.mediaUrl(s.export_path), "_blank");
      }
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  if (!character) {
    return <div className="text-slate-400">{error || "Loading…"}</div>;
  }

  const unlocked = character.status === "bootstrap" || character.status === "draft";
  const approvedCount = assets.filter((a) => a.decision === "approved").length;
  const hasLora = Boolean(lora?.lora_file_present || lora?.comfy_lora_name);
  const trainJob = jobs.find((j) => j.type === "lora_train");
  const lbAsset = lightbox !== null ? visible[lightbox] : null;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Link to={`/characters/${character.id}`} className="text-xs text-accent-soft">
            ← Edit character
          </Link>
          <h1 className="font-display mt-1 text-3xl">{character.display_name}</h1>
          <p className="mt-1 text-sm text-slate-400">
            Content studio · status{" "}
            <span className="capitalize text-slate-200">{character.status}</span>
            {unlocked && (
              <span className="ml-2 rounded-full bg-amber-500/20 px-2 py-0.5 text-xs text-amber-200">
                Unlocked / bootstrap path — identity will drift until LoRA lock
              </span>
            )}
            {character.status === "ready" && (
              <span className="ml-2 rounded-full bg-emerald-500/20 px-2 py-0.5 text-xs text-emerald-200">
                Locked production
              </span>
            )}
            {hasLora && (
              <span className="ml-2 rounded-full bg-violet-500/20 px-2 py-0.5 text-xs text-violet-200">
                LoRA active
              </span>
            )}
          </p>
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-red-500/30 bg-red-950/40 px-4 py-3 text-sm text-red-200">
          {error}
        </div>
      )}
      {info && (
        <div className="rounded-xl border border-emerald-500/30 bg-emerald-950/30 px-4 py-3 text-sm text-emerald-100">
          {info}
        </div>
      )}

      {jobs[0]?.status === "failed" && jobs[0].error_message && (
        <div className="rounded-xl border border-red-500/30 bg-red-950/40 px-4 py-3 text-sm text-red-200">
          Last job failed: {jobs[0].error_message}
        </div>
      )}

      {!!activeJobs.length && (
        <div className="rounded-xl border border-sky-500/30 bg-sky-950/30 px-4 py-3 text-sm text-sky-100">
          Generating {activeJobs.length} job(s) — first still can take several minutes
          (Comfy start + Krea load). Watch Recent jobs below.
          {activeJobs.map((j) => {
            const done = j.items.filter((i) => i.status === "done").length;
            return (
              <span key={j.id} className="mt-1 block font-mono text-xs">
                {j.type} {j.status} {done}/{j.items.length}
                {j.error_message ? ` — ${j.error_message}` : ""}
                <button
                  type="button"
                  className="ml-2 underline"
                  onClick={() => void api.cancelJob(j.id).then(() => refresh())}
                >
                  cancel
                </button>
              </span>
            );
          })}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="card space-y-4 p-5">
          <h2 className="font-display text-xl">Seed gallery</h2>
          <p className="text-sm text-slate-400">
            Generate reference candidates. Approve the most photoreal, consistent faces for LoRA
            training.
          </p>
          <button className="btn-primary" disabled={busy} onClick={() => void runSeed()}>
            Generate seed set (6)
          </button>
        </section>

        <section className="card space-y-4 p-5">
          <h2 className="font-display text-xl">Batch stills</h2>
          <p className="text-xs text-slate-500">
            Add brief lines (theme × count). Location, pose, and extra request go into CLIP-L
            so Flux actually sees what you asked for.
          </p>
          {lines.map((line, idx) => (
            <div key={idx} className="space-y-2 rounded-xl bg-white/[0.03] p-3">
              <div className="grid gap-2 sm:grid-cols-[1fr_5rem_1fr_auto]">
                <select
                  className="input"
                  value={line.theme}
                  onChange={(e) => {
                    const next = [...lines];
                    next[idx] = { ...line, theme: e.target.value };
                    setLines(next);
                  }}
                >
                  {THEMES.map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </select>
                <input
                  type="number"
                  min={1}
                  max={40}
                  className="input"
                  value={line.count}
                  onChange={(e) => {
                    const next = [...lines];
                    next[idx] = { ...line, count: Number(e.target.value) };
                    setLines(next);
                  }}
                />
                <input
                  className="input"
                  value={line.outfit}
                  placeholder="outfit hint"
                  onChange={(e) => {
                    const next = [...lines];
                    next[idx] = { ...line, outfit: e.target.value };
                    setLines(next);
                  }}
                />
                <button
                  type="button"
                  className="btn-ghost px-2"
                  disabled={lines.length === 1}
                  onClick={() => setLines(lines.filter((_, i) => i !== idx))}
                >
                  ✕
                </button>
              </div>
              <div className="grid gap-2 sm:grid-cols-3">
                <input
                  className="input"
                  value={line.location}
                  placeholder="location (e.g. park in daylight)"
                  onChange={(e) => {
                    const next = [...lines];
                    next[idx] = { ...line, location: e.target.value };
                    setLines(next);
                  }}
                />
                <input
                  className="input"
                  value={line.pose}
                  placeholder="pose (optional)"
                  onChange={(e) => {
                    const next = [...lines];
                    next[idx] = { ...line, pose: e.target.value };
                    setLines(next);
                  }}
                />
                <input
                  className="input"
                  value={line.extra}
                  placeholder="extra request (exact wording)"
                  onChange={(e) => {
                    const next = [...lines];
                    next[idx] = { ...line, extra: e.target.value };
                    setLines(next);
                  }}
                />
              </div>
              <label className="flex items-center gap-2 text-xs text-slate-400">
                <input
                  type="checkbox"
                  checked={line.useProduct}
                  onChange={(e) => {
                    const next = [...lines];
                    next[idx] = {
                      ...line,
                      useProduct: e.target.checked,
                      productId:
                        e.target.checked && !line.productId && products[0]
                          ? products[0].id
                          : line.productId,
                    };
                    setLines(next);
                  }}
                />
                Product reference
              </label>
              {line.useProduct && (
                <div className="grid gap-2 sm:grid-cols-[1fr_8rem_auto]">
                  <select
                    className="input"
                    value={line.productId}
                    onChange={(e) => {
                      const next = [...lines];
                      next[idx] = { ...line, productId: e.target.value };
                      setLines(next);
                    }}
                  >
                    <option value="">Select product…</option>
                    {products.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name}
                        {p.brand ? ` · ${p.brand}` : ""}
                      </option>
                    ))}
                  </select>
                  <select
                    className="input"
                    value={line.productPlacement}
                    onChange={(e) => {
                      const next = [...lines];
                      next[idx] = { ...line, productPlacement: e.target.value };
                      setLines(next);
                    }}
                  >
                    {PRODUCT_PLACEMENT_OPTIONS.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.label}
                      </option>
                    ))}
                  </select>
                  {line.productId &&
                    (() => {
                      const p = products.find((x) => x.id === line.productId);
                      const thumb = p?.thumb_path || p?.primary_path;
                      return thumb ? (
                        <img
                          src={api.mediaUrl(thumb)}
                          alt=""
                          className="h-10 w-10 rounded-lg object-contain bg-black/30"
                        />
                      ) : (
                        <span className="text-xs text-slate-500">—</span>
                      );
                    })()}
                </div>
              )}
            </div>
          ))}
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              className="btn-ghost text-xs"
              onClick={() =>
                setLines([
                  ...lines,
                  {
                    theme: "portrait",
                    count: 2,
                    outfit: "",
                    location: "",
                    extra: "",
                    pose: "",
                    useProduct: false,
                    productId: "",
                    productPlacement: "holding",
                  },
                ])
              }
            >
              Add line
            </button>
            <button className="btn-primary" disabled={busy} onClick={() => void runBatch()}>
              Generate batch
            </button>
            <Link to="/products" className="btn-ghost text-xs">
              Manage products
            </Link>
          </div>
          {products.length === 0 && (
            <p className="text-xs text-amber-200/80">
              No products uploaded yet. Add one under Products to enable product references.
            </p>
          )}
          <p className="text-xs text-slate-500">
            {hasLora
              ? `Using character LoRA (${lora?.comfy_lora_name}) + trigger ${lora?.trigger_word}`
              : "No LoRA yet — identity will drift until you train and register one."}
          </p>
        </section>
      </div>

      <section className="card space-y-4 p-5">
        <h2 className="font-display text-xl">Still quality</h2>
        <p className="text-sm text-slate-400">
          Keep CFG at 1.0 on stock Flux.1-dev. After a de-distilled checkpoint, raise CFG
          to about 3–4 so the negative prompt applies. Hi-res now decodes to pixels, optionally
          runs an upscale model from Comfy <code>models/upscale_models</code>, then refines.
          PuLID uses a generate-only face ref and a file in Comfy <code>models/pulid</code>.
        </p>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <label className="label">CFG (sampler)</label>
            <input
              type="number"
              min={1}
              max={8}
              step={0.1}
              className="input"
              value={fluxKnobs.cfg}
              onChange={(e) => patchFlux({ cfg: Number(e.target.value) })}
            />
          </div>
          <div>
            <label className="label">Guidance</label>
            <input
              type="number"
              min={1}
              max={5}
              step={0.1}
              className="input"
              value={fluxKnobs.guidance}
              onChange={(e) => patchFlux({ guidance: Number(e.target.value) })}
            />
          </div>
          <div>
            <label className="label">Steps</label>
            <input
              type="number"
              min={20}
              max={60}
              step={1}
              className="input"
              value={fluxKnobs.steps}
              onChange={(e) => patchFlux({ steps: Number(e.target.value) })}
            />
          </div>
          <div>
            <label className="label">Hi-res denoise</label>
            <input
              type="number"
              min={0.15}
              max={0.7}
              step={0.05}
              className="input"
              value={fluxKnobs.hires_denoise}
              onChange={(e) => patchFlux({ hires_denoise: Number(e.target.value) })}
            />
          </div>
        </div>
        <div className="grid gap-3 sm:grid-cols-[auto_1fr_auto] sm:items-end">
          <label className="flex items-center gap-2 text-sm text-slate-300">
            <input
              type="checkbox"
              checked={fluxKnobs.hires_fix}
              onChange={(e) => patchFlux({ hires_fix: e.target.checked })}
            />
            Hi-res pass
          </label>
          <div>
            <label className="label">Detail LoRA filename</label>
            <input
              className="input font-mono text-xs"
              placeholder="optional — e.g. flux_skin_detail.safetensors"
              value={fluxKnobs.detail_lora_name}
              onChange={(e) => patchFlux({ detail_lora_name: e.target.value })}
            />
          </div>
          <div>
            <label className="label">Detail strength</label>
            <input
              type="number"
              min={0}
              max={1.2}
              step={0.05}
              className="input w-24"
              value={fluxKnobs.detail_lora_strength}
              onChange={(e) => patchFlux({ detail_lora_strength: Number(e.target.value) })}
            />
          </div>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className="sm:col-span-2">
            <label className="label">Upscale model filename</label>
            <input
              className="input font-mono text-xs"
              placeholder="optional — e.g. 4x-UltraSharp.pth"
              value={fluxKnobs.upscale_model_name}
              onChange={(e) => patchFlux({ upscale_model_name: e.target.value })}
            />
          </div>
          <div className="sm:col-span-2">
            <label className="label">PuLID model filename</label>
            <input
              className="input font-mono text-xs"
              placeholder="optional — e.g. pulid_flux_v0.9.1.safetensors"
              value={fluxKnobs.pulid_model_name}
              onChange={(e) => patchFlux({ pulid_model_name: e.target.value })}
            />
          </div>
          <div>
            <label className="label">PuLID strength</label>
            <input
              type="number"
              min={0}
              max={2}
              step={0.05}
              className="input"
              value={fluxKnobs.pulid_strength}
              onChange={(e) => patchFlux({ pulid_strength: Number(e.target.value) })}
            />
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            className="btn-primary"
            disabled={busy || !fluxDirty}
            onClick={() => void saveStillQuality()}
          >
            Save quality settings
          </button>
          {fluxDirty && <span className="text-xs text-amber-200">Unsaved</span>}
        </div>
        <p className="text-xs text-slate-500">
          Identity drift after the second pass: lower hi-res denoise to 0.25–0.35 before raising
          character LoRA strength. Empty upscale model uses lanczos (still sharper than latent
          nearest-exact). PuLID stays off until a model filename is set and a face ref exists.
        </p>
      </section>

      <section className="card space-y-4 p-5">
        <h2 className="font-display text-xl">Identity LoRA</h2>
        <p className="text-sm text-slate-400">
          Lock face/body consistency: approve 12–30 photo-quality stills, then train on this machine
          (Ostris AI Toolkit on the L40S). The worker registers the LoRA when training finishes.
        </p>
        <div className="grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
          <div className="rounded-xl bg-white/5 px-3 py-2">
            <div className="text-xs text-slate-500">Approved stills</div>
            <div className="text-lg font-semibold">
              {lora?.approved_stills ?? approvedCount}
              <span className="text-xs font-normal text-slate-500">
                {" "}
                / {lora?.recommended_min ?? 12} rec.
              </span>
            </div>
          </div>
          <div className="rounded-xl bg-white/5 px-3 py-2">
            <div className="text-xs text-slate-500">Dataset images</div>
            <div className="text-lg font-semibold">{lora?.dataset_images ?? 0}</div>
          </div>
          <div className="rounded-xl bg-white/5 px-3 py-2">
            <div className="text-xs text-slate-500">Trigger word</div>
            <div className="truncate font-mono text-sm text-accent-soft">
              {lora?.trigger_word || "—"}
            </div>
          </div>
          <div className="rounded-xl bg-white/5 px-3 py-2">
            <div className="text-xs text-slate-500">Comfy LoRA</div>
            <div className="truncate font-mono text-sm">
              {lora?.comfy_lora_name || (hasLora ? "registered" : "not installed")}
            </div>
          </div>
        </div>
        {lora?.coverage && (
          <div>
            <div className="mb-1 text-xs uppercase tracking-wide text-slate-500">
              Dataset coverage (from approved prompts)
            </div>
            <div className="flex flex-wrap gap-1.5">
              {Object.entries(lora.coverage).map(([k, ok]) => (
                <span
                  key={k}
                  className={`rounded-full px-2 py-0.5 text-[10px] ${
                    ok ? "bg-emerald-500/20 text-emerald-200" : "bg-white/5 text-slate-500"
                  }`}
                >
                  {ok ? "✓ " : "○ "}
                  {k}
                </span>
              ))}
            </div>
          </div>
        )}
        <div className="flex flex-wrap items-end gap-2">
          <div>
            <label className="label">Train steps</label>
            <input
              type="number"
              min={200}
              max={4000}
              step={100}
              className="input w-28"
              value={trainSteps}
              onChange={(e) => setTrainSteps(Number(e.target.value))}
            />
          </div>
          <button
            type="button"
            className="btn-primary"
            disabled={busy || approvedCount < 4}
            onClick={() => void trainAndRegister()}
          >
            Train LoRA & register
          </button>
          <button
            type="button"
            className="btn-ghost"
            disabled={busy || approvedCount < 4}
            onClick={() => void buildDataset()}
          >
            Build dataset only
          </button>
        </div>
        {trainJob && (
          <div
            className={`rounded-xl px-3 py-2 text-sm ${
              trainJob.status === "failed"
                ? "border border-red-500/30 bg-red-950/40 text-red-200"
                : trainJob.status === "completed"
                  ? "border border-emerald-500/30 bg-emerald-950/30 text-emerald-100"
                  : "border border-sky-500/30 bg-sky-950/30 text-sky-100"
            }`}
          >
            Train job <span className="font-mono">{trainJob.id.slice(0, 8)}</span> · {trainJob.status}
            {trainJob.error_message ? ` — ${trainJob.error_message}` : ""}
            {trainJob.status === "queued" && (
              <div className="mt-1 text-xs text-sky-200/80">
                Queued but GPU is idle means no CUDA worker is listening. On nemesis:
                <pre className="mt-1 overflow-x-auto rounded bg-black/30 p-2 text-[11px]">
                  {`docker stop instantimpact-worker
cd /home/pkeener/InstantImpact/apps/worker
../../.venv/bin/python -m worker.main`}
                </pre>
              </div>
            )}
          </div>
        )}
        {lora?.toolkit_ready === false && (
          <p className="text-xs text-amber-200">
            AI Toolkit not visible to the API (Docker cannot see the host folder unless it is mounted).
            On nemesis: clone ostris/ai-toolkit to <code>/home/pkeener/ai-toolkit</code>, add{" "}
            <code>INSTANTIMPACT_AI_TOOLKIT_DIR=/home/pkeener/ai-toolkit</code> to <code>.env</code>,
            and run a <strong>native</strong> GPU worker (not the Compose worker).
          </p>
        )}
        <div className="grid gap-3 sm:grid-cols-[1fr_auto_auto]">
          <div>
            <label className="label">Trained LoRA path (under data/ or Comfy loras dir)</label>
            <input
              className="input font-mono text-xs"
              placeholder="data/characters/…/lora/model.safetensors"
              value={loraPath}
              onChange={(e) => setLoraPath(e.target.value)}
            />
          </div>
          <div>
            <label className="label">Strength</label>
            <input
              type="number"
              min={0}
              max={2}
              step={0.05}
              className="input w-24"
              value={loraStrength}
              onChange={(e) => setLoraStrength(Number(e.target.value))}
            />
          </div>
          <div className="flex items-end">
            <button
              type="button"
              className="btn-ghost w-full"
              disabled={busy || !loraPath.trim()}
              onClick={() => void registerLora()}
            >
              Register LoRA
            </button>
          </div>
        </div>
        <ol className="list-decimal space-y-1 pl-5 text-xs text-slate-500">
          <li>Approve photoreal stills (reject cartoons / bad faces). Aim for coverage badges above.</li>
          <li>
            Click <strong>Train LoRA & register</strong> (builds dataset, trains on the GPU worker, copies
            weights into Comfy). Training takes ~20–90 minutes; stills wait on the GPU lock.
          </li>
          <li>The native GPU worker must be running (not the Docker CPU worker). Comfy is unloaded for the train.</li>
          <li>When the job completes, lock the character (edit → safety lock) and generate with the LoRA.</li>
        </ol>
      </section>

      <section className="card space-y-4 p-5">
        <h2 className="font-display text-xl">Marketing voice → ad copy</h2>
        <p className="text-sm text-slate-400">
          Generate captions in this character&apos;s reusable voice. Set the voice under Edit →
          Personality, then use it across products and stills.
        </p>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <label className="block space-y-1 text-sm">
            <span className="text-slate-500">Product (optional)</span>
            <select
              className="input"
              value={adProductId}
              onChange={(e) => setAdProductId(e.target.value)}
            >
              <option value="">No product</option>
              {products.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
          <label className="block space-y-1 text-sm">
            <span className="text-slate-500">Theme</span>
            <select className="input" value={adTheme} onChange={(e) => setAdTheme(e.target.value)}>
              {THEMES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </label>
          <label className="block space-y-1 text-sm">
            <span className="text-slate-500">Attach to still</span>
            <select
              className="input"
              value={captionAssetId}
              onChange={(e) => setCaptionAssetId(e.target.value)}
            >
              <option value="">Select output…</option>
              {assets.slice(0, 40).map((a) => (
                <option key={a.id} value={a.id}>
                  {(a.meta?.marketing_caption ? "✓ " : "") +
                    `seed ${a.seed ?? "?"} · ${a.decision}`}
                </option>
              ))}
            </select>
          </label>
          <div className="flex items-end gap-2">
            <button
              type="button"
              className="btn-primary"
              disabled={busy}
              onClick={() => void runAdCopy()}
            >
              Generate copy
            </button>
            <Link to={id ? `/characters/${id}` : "/characters"} className="btn-ghost text-xs">
              Edit voice
            </Link>
          </div>
        </div>
        {adCopy && (
          <div className="space-y-3">
            <textarea
              className="input min-h-[100px]"
              value={adCaptionEdit}
              onChange={(e) => setAdCaptionEdit(e.target.value)}
            />
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                className="btn-primary"
                disabled={busy || !captionAssetId}
                onClick={() => void saveCaptionToAsset()}
              >
                Save caption to still
              </button>
              {adCopy.variants.slice(1).map((v, i) => (
                <button
                  key={i}
                  type="button"
                  className="btn-ghost text-xs"
                  onClick={() => setAdCaptionEdit(v.caption)}
                >
                  Variant {i + 2}
                </button>
              ))}
            </div>
            <p className="text-xs text-slate-500">
              Tone: {adCopy.tone || "—"} · CTA: {adCopy.cta_style || "—"}
              {adCopy.product_name ? ` · Product: ${adCopy.product_name}` : ""}
            </p>
          </div>
        )}
      </section>

      <section className="card p-5">
        <h2 className="font-display text-xl">Recent jobs</h2>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase text-slate-500">
              <tr>
                <th className="py-2 pr-4">Type</th>
                <th className="py-2 pr-4">Status</th>
                <th className="py-2 pr-4">Items</th>
                <th className="py-2 pr-4">Created</th>
                <th className="py-2 pr-4">Detail</th>
                <th className="py-2"> </th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((j) => (
                <tr key={j.id} className="border-t border-white/5">
                  <td className="py-2 pr-4 font-mono text-xs">{j.type}</td>
                  <td className="py-2 pr-4 capitalize">{j.status}</td>
                  <td className="py-2 pr-4">
                    {j.items.filter((i) => i.status === "done").length}/{j.items.length}
                  </td>
                  <td className="py-2 pr-4 text-slate-500">{new Date(j.created_at).toLocaleString()}</td>
                  <td className="max-w-xs py-2 pr-4 text-xs text-amber-200/90">
                    {j.error_message || ""}
                  </td>
                  <td className="py-2">
                    {(j.status === "queued" || j.status === "running") && (
                      <button
                        type="button"
                        className="btn-ghost px-2 py-1 text-[10px]"
                        onClick={() => void api.cancelJob(j.id).then(() => refresh())}
                      >
                        Cancel
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {!jobs.length && (
                <tr>
                  <td colSpan={6} className="py-4 text-slate-500">
                    No jobs yet
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="font-display text-xl">Outputs</h2>
          <div className="flex flex-wrap items-center gap-2">
            {FILTERS.map((f) => (
              <button
                key={f}
                type="button"
                className={`rounded-full px-2.5 py-0.5 text-xs capitalize ${
                  filter === f ? "bg-accent text-white" : "bg-white/5 text-slate-400"
                }`}
                onClick={() => setFilter(f)}
              >
                {f}
              </button>
            ))}
            <button
              type="button"
              className={`rounded-full px-2.5 py-0.5 text-xs ${
                assetSort === "newest" ? "bg-accent text-white" : "bg-white/5 text-slate-400"
              }`}
              onClick={() => setAssetSort("newest")}
            >
              newest
            </button>
            <button
              type="button"
              className={`rounded-full px-2.5 py-0.5 text-xs ${
                assetSort === "match" ? "bg-accent text-white" : "bg-white/5 text-slate-400"
              }`}
              onClick={() => setAssetSort("match")}
            >
              best match
            </button>
            <button
              type="button"
              className="btn-ghost text-xs text-red-300/90 hover:text-red-200"
              disabled={busy || !assets.some((a) => a.decision === "rejected")}
              onClick={() => void deleteRejected()}
            >
              Delete all rejected
            </button>
          </div>
        </div>
        <p className="mt-2 text-xs text-slate-500">
          Click a still for prompt/seed. Keys in lightbox: ← → · A approve · R reject · Esc.
        </p>
        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
          {visible.map((a, idx) => (
            <div key={a.id} className="overflow-hidden rounded-xl border border-white/10 bg-black/30">
              <button type="button" className="block w-full" onClick={() => setLightbox(idx)}>
                {a.thumb_path || a.path ? (
                  <img
                    src={api.mediaUrl(a.thumb_path || a.path)}
                    alt=""
                    className="aspect-[3/4] w-full object-cover"
                  />
                ) : (
                  <div className="aspect-[3/4] bg-ink-800" />
                )}
              </button>
              <div className="space-y-2 p-2">
                <label className="flex items-center gap-2 text-[10px] text-slate-500">
                  <input
                    type="checkbox"
                    checked={!!selected[a.id]}
                    onChange={(e) => setSelected({ ...selected, [a.id]: e.target.checked })}
                  />
                  seed {a.seed ?? "—"}
                  {a.meta?.marketing_caption ? (
                    <span className="rounded bg-emerald-500/15 px-1 text-emerald-200">caption</span>
                  ) : null}
                  {a.consistency_score != null && (
                    <span className="ml-auto text-accent-soft">
                      {(a.consistency_score * 100).toFixed(0)}%
                    </span>
                  )}
                </label>
                {typeof a.meta?.marketing_caption === "string" && (
                  <p className="line-clamp-2 text-[10px] text-slate-400">
                    {a.meta.marketing_caption}
                  </p>
                )}
                <div className="flex gap-1">
                  <button
                    type="button"
                    className="btn-ghost flex-1 px-1 py-1 text-[10px]"
                    disabled={busy}
                    onClick={() => void decide(a.id, "approved")}
                  >
                    ✓
                  </button>
                  <button
                    type="button"
                    className="btn-ghost flex-1 px-1 py-1 text-[10px]"
                    disabled={busy}
                    onClick={() => void decide(a.id, "rejected")}
                  >
                    ✕
                  </button>
                  <button
                    type="button"
                    className="btn-ghost flex-1 px-1 py-1 text-[10px] text-red-300/90"
                    disabled={busy}
                    onClick={() => void removeAsset(a.id)}
                  >
                    🗑
                  </button>
                </div>
                <div className="text-center text-[10px] capitalize text-slate-400">{a.decision}</div>
              </div>
            </div>
          ))}
          {!visible.length && <p className="col-span-full text-sm text-slate-500">No assets yet</p>}
        </div>
      </section>

      <section className="card space-y-4 p-5">
        <h2 className="font-display text-xl">Approved sets & export</h2>
        <p className="text-sm text-slate-400">
          Select approved stills above, create an immutable set (copied + hashed), then export a zip
          with disclosure sidecars.
        </p>
        <div className="flex flex-wrap gap-2">
          <input
            className="input max-w-xs"
            value={setTitle}
            onChange={(e) => setSetTitle(e.target.value)}
            placeholder="Set title"
          />
          <button type="button" className="btn-primary" disabled={busy} onClick={() => void makeSet()}>
            Create set from selection
          </button>
        </div>
        <label className="flex items-start gap-2 text-sm text-slate-300">
          <input
            type="checkbox"
            className="mt-1"
            checked={exportConfirm}
            onChange={(e) => setExportConfirm(e.target.checked)}
          />
          I confirm all assets in the export depict a clearly adult synthetic persona (21+).
        </label>
        <ul className="space-y-2 text-sm">
          {sets.map((s) => (
            <li
              key={s.id}
              className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-white/5 px-3 py-2"
            >
              <div>
                <div className="font-medium">{s.title}</div>
                <div className="text-xs text-slate-500">
                  {s.item_count} files
                  {s.export_path ? ` · exported ${s.export_path}` : " · not exported"}
                </div>
              </div>
              <button
                type="button"
                className="btn-ghost text-xs"
                disabled={busy || !exportConfirm}
                onClick={() => void doExport(s.id)}
              >
                Export zip
              </button>
            </li>
          ))}
          {!sets.length && <li className="text-slate-500">No approved sets yet</li>}
        </ul>
      </section>

      {lbAsset && lightbox !== null && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4"
          onClick={() => setLightbox(null)}
        >
          <div
            className="max-h-[92vh] w-full max-w-4xl overflow-auto rounded-2xl border border-white/10 bg-ink-900 p-4"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="grid gap-4 md:grid-cols-2">
              <img
                src={api.mediaUrl(lbAsset.path)}
                alt=""
                className="w-full rounded-xl object-contain"
              />
              <div className="space-y-3 text-sm">
                <div className="text-xs uppercase text-slate-500">
                  {lightbox + 1} / {visible.length} · {lbAsset.decision}
                </div>
                <div>
                  Seed <span className="font-mono">{lbAsset.seed ?? "—"}</span>
                  {lbAsset.consistency_score != null && (
                    <span className="ml-2 text-accent-soft">
                      ref similarity {(lbAsset.consistency_score * 100).toFixed(0)}%
                    </span>
                  )}
                </div>
                <div>
                  <div className="text-xs text-emerald-400">Positive</div>
                  <p className="mt-1 text-xs text-slate-300">{lbAsset.prompt_positive || "—"}</p>
                </div>
                <div>
                  <div className="text-xs text-rose-400">Negative</div>
                  <p className="mt-1 text-xs text-slate-400">{lbAsset.prompt_negative || "—"}</p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button className="btn-primary text-xs" onClick={() => void decide(lbAsset.id, "approved")}>
                    Approve (A)
                  </button>
                  <button className="btn-ghost text-xs" onClick={() => void decide(lbAsset.id, "rejected")}>
                    Reject (R)
                  </button>
                  <button
                    className="btn-ghost text-xs"
                    disabled={busy || !id}
                    onClick={() =>
                      id &&
                      void api
                        .regenerate(id, lbAsset.id, 1)
                        .then(() => refresh())
                        .catch((e) => setError(e.message))
                    }
                  >
                    Regenerate seed
                  </button>
                  <button className="btn-ghost text-xs text-red-300" onClick={() => void removeAsset(lbAsset.id)}>
                    Delete
                  </button>
                  <button className="btn-ghost text-xs" onClick={() => setLightbox(null)}>
                    Close
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, Asset, Character, Job } from "../api";

export default function CharacterStudio() {
  const { id } = useParams();
  const [character, setCharacter] = useState<Character | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [batchCount, setBatchCount] = useState(4);
  const [theme, setTheme] = useState("casual_bedroom");
  const [outfit, setOutfit] = useState("oversized tee");

  const refresh = useCallback(async () => {
    if (!id) return;
    const [c, j, a] = await Promise.all([
      api.getCharacter(id),
      api.listJobs(id),
      api.listAssets(id),
    ]);
    setCharacter(c);
    setJobs(j);
    setAssets(a);
  }, [id]);

  useEffect(() => {
    refresh().catch((e) => setError(e.message));
  }, [refresh]);

  async function runSeed() {
    if (!id) return;
    setBusy(true);
    setError(null);
    try {
      await api.seedGallery(id, { count: 6, themes: ["portrait", "glamour", "casual_bedroom"] });
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function runBatch() {
    if (!id) return;
    setBusy(true);
    setError(null);
    try {
      await api.stillBatch(id, {
        title: `${theme} batch`,
        aspect_ratio: "4:5",
        items: [
          {
            type: "still",
            count: batchCount,
            theme,
            outfit_hint: outfit,
            pose_hint: "relaxed natural pose",
            location_hint: undefined,
          },
        ],
      });
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
    if (
      !window.confirm(
        `Permanently delete ${n} rejected image(s) from the library and disk?`
      )
    ) {
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

  if (!character) {
    return <div className="text-slate-400">{error || "Loading…"}</div>;
  }

  const unlocked = character.status === "bootstrap" || character.status === "draft";

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
                Unlocked / bootstrap path
              </span>
            )}
            {character.status === "ready" && (
              <span className="ml-2 rounded-full bg-emerald-500/20 px-2 py-0.5 text-xs text-emerald-200">
                Locked production
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

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="card space-y-4 p-5">
          <h2 className="font-display text-xl">Seed gallery</h2>
          <p className="text-sm text-slate-400">
            Generate-only reference candidates for consistency (mock placeholders until Flux
            workflow is pinned).
          </p>
          <button className="btn-primary" disabled={busy} onClick={runSeed}>
            Generate seed set (6)
          </button>
        </section>

        <section className="card space-y-4 p-5">
          <h2 className="font-display text-xl">Batch stills</h2>
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label className="label">Theme</label>
              <select className="input" value={theme} onChange={(e) => setTheme(e.target.value)}>
                {[
                  "portrait",
                  "casual_bedroom",
                  "lingerie_set",
                  "outdoor_day",
                  "glamour",
                  "mirror_selfie",
                ].map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="label">Count</label>
              <input
                type="number"
                min={1}
                max={40}
                className="input"
                value={batchCount}
                onChange={(e) => setBatchCount(Number(e.target.value))}
              />
            </div>
          </div>
          <div>
            <label className="label">Outfit hint</label>
            <input className="input" value={outfit} onChange={(e) => setOutfit(e.target.value)} />
          </div>
          <button className="btn-primary" disabled={busy} onClick={runBatch}>
            Generate batch
          </button>
          <p className="text-xs text-slate-500">
            Requires bootstrap or ready + safety confirmations. Draft blocks still_batch.
          </p>
        </section>
      </div>

      <section className="card p-5">
        <h2 className="font-display text-xl">Recent jobs</h2>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase text-slate-500">
              <tr>
                <th className="py-2 pr-4">Type</th>
                <th className="py-2 pr-4">Status</th>
                <th className="py-2 pr-4">Items</th>
                <th className="py-2">Created</th>
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
                  <td className="py-2 text-slate-500">{new Date(j.created_at).toLocaleString()}</td>
                </tr>
              ))}
              {!jobs.length && (
                <tr>
                  <td colSpan={4} className="py-4 text-slate-500">
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
          <button
            type="button"
            className="btn-ghost text-xs text-red-300/90 hover:text-red-200"
            disabled={busy || !assets.some((a) => a.decision === "rejected")}
            onClick={() => void deleteRejected()}
          >
            Delete all rejected
          </button>
        </div>
        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
          {assets.map((a) => (
            <div key={a.id} className="overflow-hidden rounded-xl border border-white/10 bg-black/30">
              {a.thumb_path || a.path ? (
                <img
                  src={api.mediaUrl(a.thumb_path || a.path)}
                  alt=""
                  className="aspect-[3/4] w-full object-cover"
                />
              ) : (
                <div className="aspect-[3/4] bg-ink-800" />
              )}
              <div className="space-y-2 p-2">
                <div className="truncate text-[10px] text-slate-500">seed {a.seed ?? "—"}</div>
                <div className="flex gap-1">
                  <button
                    type="button"
                    className="btn-ghost flex-1 px-1 py-1 text-[10px]"
                    disabled={busy}
                    onClick={() => void decide(a.id, "approved")}
                    title="Approve"
                  >
                    ✓
                  </button>
                  <button
                    type="button"
                    className="btn-ghost flex-1 px-1 py-1 text-[10px]"
                    disabled={busy}
                    onClick={() => void decide(a.id, "rejected")}
                    title="Reject"
                  >
                    ✕
                  </button>
                  <button
                    type="button"
                    className="btn-ghost flex-1 px-1 py-1 text-[10px] text-red-300/90"
                    disabled={busy}
                    onClick={() => void removeAsset(a.id)}
                    title="Delete permanently"
                  >
                    🗑
                  </button>
                </div>
                <div className="text-center text-[10px] capitalize text-slate-400">{a.decision}</div>
              </div>
            </div>
          ))}
          {!assets.length && <p className="col-span-full text-sm text-slate-500">No assets yet</p>}
        </div>
      </section>
    </div>
  );
}

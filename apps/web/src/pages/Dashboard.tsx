import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, Character } from "../api";

export default function Dashboard() {
  const nav = useNavigate();
  const [health, setHealth] = useState<Record<string, unknown> | null>(null);
  const [chars, setChars] = useState<Character[]>([]);
  const [gpu, setGpu] = useState<string>("…");
  const [error, setError] = useState<string | null>(null);
  const [busyRandom, setBusyRandom] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const [h, c, g] = await Promise.all([api.health(), api.listCharacters(), api.gpu()]);
        setHealth(h as unknown as Record<string, unknown>);
        setChars(c);
        setGpu(
          g.mock_generation
            ? "Mock generation ON (no ComfyUI required)"
            : g.comfy_enabled
              ? "ComfyUI mode"
              : g.message
        );
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    })();
  }, []);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="font-display text-3xl text-white">Studio dashboard</h1>
        <p className="mt-2 max-w-2xl text-slate-400">
          Design synthetic adult personas, lock identity with Flux + LoRA, and batch stills — fully
          local. MVP ships stills first; video & captions follow.
        </p>
      </div>

      {error && (
        <div className="card border-red-500/30 bg-red-950/30 p-4 text-sm text-red-200">
          API unreachable: {error}. Start the API with{" "}
          <code className="text-red-100">scripts/dev_up.ps1</code> or{" "}
          <code className="text-red-100">uvicorn</code>.
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-3">
        <div className="card p-5">
          <div className="text-xs uppercase tracking-wide text-slate-500">Health</div>
          <div className="mt-2 text-2xl font-semibold text-emerald-400">
            {(health?.status as string) || "—"}
          </div>
          <div className="mt-1 text-xs text-slate-500">control plane (prefer nemesis)</div>
        </div>
        <div className="card p-5">
          <div className="text-xs uppercase tracking-wide text-slate-500">Characters</div>
          <div className="mt-2 text-2xl font-semibold">{chars.length}</div>
          <div className="mt-1 text-xs text-slate-500">active library</div>
        </div>
        <div className="card p-5">
          <div className="text-xs uppercase tracking-wide text-slate-500">GPU / gen</div>
          <div className="mt-2 text-sm font-medium text-accent-soft">{gpu}</div>
          <div className="mt-1 text-xs text-slate-500">L40S path · mock until Comfy pinned</div>
        </div>
      </div>

      <div className="flex flex-wrap gap-3">
        <Link to="/characters/new" className="btn-primary">
          Create character
        </Link>
        <button
          type="button"
          className="btn-ghost"
          disabled={busyRandom}
          onClick={() => {
            setBusyRandom(true);
            setError(null);
            api
              .createRandomCharacter({ auto_attest: true, auto_bootstrap: true })
              .then((c) => nav(`/characters/${c.id}`))
              .catch((e) => setError(e instanceof Error ? e.message : String(e)))
              .finally(() => setBusyRandom(false));
          }}
        >
          {busyRandom ? "Rolling…" : "Random character"}
        </button>
        <Link to="/characters" className="btn-ghost">
          Manage library
        </Link>
      </div>

      <section className="card p-6">
        <h2 className="font-display text-xl">MVP workflow</h2>
        <ol className="mt-4 grid gap-3 text-sm text-slate-300 sm:grid-cols-2">
          {[
            "Create persona (21+, synthetic attestation)",
            "Design appearance & boundaries",
            "Bootstrap → seed gallery (mock or Flux)",
            "Train LoRA & human lock (PR-08 path)",
            "Content brief → batch stills",
            "Review, approve, export with disclosure",
          ].map((step, i) => (
            <li key={step} className="flex gap-3 rounded-xl bg-white/5 px-3 py-2">
              <span className="text-accent-soft">{i + 1}.</span>
              <span>{step}</span>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}

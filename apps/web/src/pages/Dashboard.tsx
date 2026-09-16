import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, Character, Health } from "../api";

export default function Dashboard() {
  const nav = useNavigate();
  const [health, setHealth] = useState<Health | null>(null);
  const [chars, setChars] = useState<Character[]>([]);
  const [gpu, setGpu] = useState<string>("…");
  const [error, setError] = useState<string | null>(null);
  const [busyRandom, setBusyRandom] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const [h, c, g] = await Promise.all([api.health(), api.listCharacters(), api.gpu()]);
        setHealth(h);
        setChars(c);
        setGpu(
          g.mock_generation
            ? "Mock generation ON (no ComfyUI required)"
            : g.comfy_healthy === false
              ? "ComfyUI down — start it on :8188"
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
          <div>API unreachable: {error}</div>
          <p className="mt-2 text-xs text-red-200/80">
            On nemesis the API is usually <code>:8001</code> (vLLM often owns <code>:8000</code>).
            Restart web after the API is up, or set{" "}
            <code>VITE_API_PROXY=http://127.0.0.1:8001</code>. Native:{" "}
            <code>bash scripts/ii start --stop-vllm</code>. Docker:{" "}
            <code>docker compose up -d api worker web</code> (host Redis, not a second Redis).
          </p>
        </div>
      )}

      {health?.comfy_healthy === false && (
        <div className="card border-amber-500/30 bg-amber-950/30 p-4 text-sm text-amber-100">
          ComfyUI is not reachable at <code className="text-amber-50">127.0.0.1:8188</code>. Docker
          Compose does not start it. On nemesis:
          <pre className="mt-2 overflow-x-auto rounded-lg bg-black/30 p-3 text-xs text-amber-50">
            {`curl -sS http://127.0.0.1:8188/system_stats
docker stop vllm 2>/dev/null
bash scripts/ii start --stop-vllm`}
          </pre>
          Then refresh this page. Health should read <strong>ok</strong> and comfy <strong>ok</strong>.
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-3">
        <div className="card p-5">
          <div className="text-xs uppercase tracking-wide text-slate-500">Health</div>
          <div
            className={`mt-2 text-2xl font-semibold ${
              health?.status === "ok"
                ? "text-emerald-400"
                : health?.status === "degraded"
                  ? "text-amber-300"
                  : "text-slate-300"
            }`}
          >
            {health?.status || "—"}
          </div>
          <div className="mt-1 text-xs text-slate-500">
            redis {health?.redis_ok ? "ok" : "down"} · comfy{" "}
            {health?.comfy_healthy === true ? "ok" : health?.comfy_healthy === false ? "down" : "n/a"}
            {health?.disk_free_gb != null ? ` · ${health.disk_free_gb} GB free` : ""}
          </div>
        </div>
        <div className="card p-5">
          <div className="text-xs uppercase tracking-wide text-slate-500">Characters</div>
          <div className="mt-2 text-2xl font-semibold">{chars.length}</div>
          <div className="mt-1 text-xs text-slate-500">active library</div>
        </div>
        <div className="card p-5">
          <div className="text-xs uppercase tracking-wide text-slate-500">GPU / gen</div>
          <div className="mt-2 text-sm font-medium text-accent-soft">{gpu}</div>
          <div className="mt-1 text-xs text-slate-500">
            {health?.comfy_healthy === true
              ? "L40S · Flux stills"
              : health?.comfy_healthy === false
                ? "Comfy required for real stills"
                : "L40S path"}
          </div>
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
              .createRandomCharacter({ auto_attest: false, auto_bootstrap: false })
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

import { useEffect, useState } from "react";
import { Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { api, apiToken, GpuStatus, setApiToken } from "./api";
import Dashboard from "./pages/Dashboard";
import CharacterList from "./pages/CharacterList";
import CharacterWizard from "./pages/CharacterWizard";
import CharacterStudio from "./pages/CharacterStudio";
import Products from "./pages/Products";

function Nav() {
  const loc = useLocation();
  const [gpu, setGpu] = useState<GpuStatus | null>(null);
  const [token, setToken] = useState(apiToken());
  const [showToken, setShowToken] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function tick() {
      try {
        const g = await api.gpu();
        if (!cancelled) setGpu(g);
      } catch {
        if (!cancelled) setGpu(null);
      }
    }
    void tick();
    const t = setInterval(tick, 5000);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, []);

  const link = (to: string, label: string) => {
    const active = loc.pathname === to || (to !== "/" && loc.pathname.startsWith(to));
    return (
      <Link
        to={to}
        className={`rounded-lg px-3 py-1.5 text-sm transition ${
          active ? "bg-white/10 text-white" : "text-slate-400 hover:text-white"
        }`}
      >
        {label}
      </Link>
    );
  };

  return (
    <header className="sticky top-0 z-20 border-b border-white/5 bg-ink-950/80 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3">
        <Link to="/" className="flex items-center gap-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent/20 text-accent-soft">
            ◆
          </span>
          <div>
            <div className="font-display text-lg leading-none tracking-tight">InstantImpact</div>
            <div className="text-[10px] uppercase tracking-widest text-slate-500">
              Local persona studio
            </div>
          </div>
        </Link>
        <nav className="flex items-center gap-1">
          {link("/", "Dashboard")}
          {link("/characters", "Characters")}
          {link("/products", "Products")}
        </nav>
        <div className="flex items-center gap-2 text-[11px] text-slate-400">
          {gpu && (
            <span
              className={`hidden rounded-full px-2 py-0.5 sm:inline ${
                gpu.locked
                  ? "bg-amber-500/20 text-amber-200"
                  : (gpu.queue_depth || 0) > 0
                    ? "bg-sky-500/20 text-sky-200"
                    : gpu.mock_generation
                      ? "bg-white/5"
                      : "bg-emerald-500/15 text-emerald-200"
              }`}
              title={gpu.message}
            >
              {gpu.mock_generation
                ? "mock"
                : gpu.locked
                  ? "GPU busy"
                  : (gpu.queue_depth || 0) > 0
                    ? `${gpu.queue_depth} queued`
                    : "GPU idle"}
            </span>
          )}
          <button type="button" className="text-slate-500 hover:text-white" onClick={() => setShowToken((s) => !s)}>
            token
          </button>
        </div>
      </div>
      {showToken && (
        <div className="mx-auto flex max-w-6xl gap-2 px-4 pb-3">
          <input
            className="input font-mono text-xs"
            placeholder="API token (LAN)"
            value={token}
            onChange={(e) => setToken(e.target.value)}
          />
          <button
            type="button"
            className="btn-ghost text-xs"
            onClick={() => {
              setApiToken(token.trim());
              setShowToken(false);
            }}
          >
            Save
          </button>
        </div>
      )}
    </header>
  );
}

export default function App() {
  return (
    <div className="min-h-screen">
      <Nav />
      <main className="mx-auto max-w-6xl px-4 py-8">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/characters" element={<CharacterList />} />
          <Route path="/characters/new" element={<CharacterWizard />} />
          <Route path="/characters/:id" element={<CharacterWizard />} />
          <Route path="/characters/:id/studio" element={<CharacterStudio />} />
          <Route path="/products" element={<Products />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}

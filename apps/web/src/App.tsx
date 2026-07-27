import { Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import CharacterList from "./pages/CharacterList";
import CharacterWizard from "./pages/CharacterWizard";
import CharacterStudio from "./pages/CharacterStudio";

function Nav() {
  const loc = useLocation();
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
        </nav>
      </div>
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
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}

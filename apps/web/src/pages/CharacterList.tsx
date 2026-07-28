import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, Character } from "../api";

const statusColor: Record<string, string> = {
  draft: "bg-slate-500/20 text-slate-300",
  bootstrap: "bg-amber-500/20 text-amber-200",
  training: "bg-sky-500/20 text-sky-200",
  ready: "bg-emerald-500/20 text-emerald-200",
  archived: "bg-zinc-500/20 text-zinc-400",
};

export default function CharacterList() {
  const nav = useNavigate();
  const [chars, setChars] = useState<Character[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .listCharacters()
      .then(setChars)
      .catch((e) => setError(e.message));
  }, []);

  async function randomCharacter() {
    setBusy(true);
    setError(null);
    try {
      const c = await api.createRandomCharacter({ auto_attest: true, auto_bootstrap: true });
      setChars((prev) => [c, ...prev]);
      nav(`/characters/${c.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-3xl">Characters</h1>
          <p className="mt-1 text-slate-400">Synthetic personas · multi-character library</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="btn-ghost"
            disabled={busy}
            onClick={() => void randomCharacter()}
          >
            {busy ? "Rolling…" : "Random character"}
          </button>
          <Link to="/characters/new" className="btn-primary">
            New character
          </Link>
        </div>
      </div>

      {error && <div className="text-sm text-red-300">{error}</div>}

      <div className="grid gap-4 sm:grid-cols-2">
        {chars.map((c) => (
          <div key={c.id} className="card p-5">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold">{c.display_name}</h2>
                <p className="text-xs text-slate-500">/{c.slug}</p>
              </div>
              <span
                className={`rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ${
                  statusColor[c.status] || statusColor.draft
                }`}
              >
                {c.status}
              </span>
            </div>
            <p className="mt-3 text-sm text-slate-400">
              {c.age_appearance_band} · min {c.age_appearance_min}+ ·{" "}
              {c.synthetic_confirmed ? "synthetic ✓" : "confirm synthetic"}
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              <Link to={`/characters/${c.id}`} className="btn-ghost text-xs">
                Edit
              </Link>
              <Link to={`/characters/${c.id}/studio`} className="btn-primary text-xs">
                Studio
              </Link>
            </div>
          </div>
        ))}
        {!chars.length && !error && (
          <div className="card col-span-full p-8 text-center text-slate-400">
            No characters yet.{" "}
            <Link to="/characters/new" className="text-accent-soft underline">
              Create one
            </Link>
          </div>
        )}
      </div>
    </div>
  );
}

import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, Character } from "../api";

const STEPS = ["Basics", "Appearance", "Personality", "Boundaries", "Safety & lock"];

const emptyForm = {
  display_name: "",
  age_appearance_min: 21,
  age_appearance_band: "mid-20s",
  synthetic_confirmed: false,
  not_real_person_attested: false,
  attestation_text: "",
  niche_tags: "" as string,
  trigger_word: "",
  appearance: {
    hair_color: "",
    hair_style: "",
    hair_length: "",
    eye_color: "",
    skin_tone: "",
    body_type: "",
    face_shape: "",
    style_keywords: "" as string,
    freeform_notes: "",
  },
  personality: {
    traits: "" as string,
    tone: "",
    bio_short: "",
  },
  boundaries: {
    hard_bans: "" as string,
    soft_limits: "" as string,
    content_allowed: "" as string,
  },
  speaking_style: {
    formality: "warm",
    emoji_use: "light",
    example_lines: "" as string,
  },
};

function splitList(s: string): string[] {
  return s
    .split(/[,;\n]/)
    .map((x) => x.trim())
    .filter(Boolean);
}

export default function CharacterWizard() {
  const { id } = useParams();
  const nav = useNavigate();
  const isNew = !id || id === "new";
  const [step, setStep] = useState(0);
  const [form, setForm] = useState(emptyForm);
  const [character, setCharacter] = useState<Character | null>(null);
  const [preview, setPreview] = useState<{ positive: string; negative: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [lockChecks, setLockChecks] = useState({
    adult: false,
    synthetic: false,
    notReal: false,
    text: "",
    dryRun: false,
  });
  const [hasLora, setHasLora] = useState(false);

  useEffect(() => {
    if (isNew) return;
    api
      .getCharacter(id!)
      .then((c) => {
        setCharacter(c);
        api.loraStatus(c.id).then((l) => setHasLora(Boolean(l.lora_file_present))).catch(() => undefined);
        const v = c.current_version;
        const a = (v?.appearance || {}) as Record<string, string | string[]>;
        const p = (v?.personality || {}) as Record<string, string | string[]>;
        const b = (v?.boundaries || {}) as Record<string, string | string[]>;
        const s = (v?.speaking_style || {}) as Record<string, string | string[]>;
        setForm({
          display_name: c.display_name,
          age_appearance_min: c.age_appearance_min,
          age_appearance_band: c.age_appearance_band,
          synthetic_confirmed: c.synthetic_confirmed,
          not_real_person_attested: c.not_real_person_attested,
          attestation_text: c.attestation_text || "",
          niche_tags: (c.niche_tags || []).join(", "),
          trigger_word: v?.trigger_word || "",
          appearance: {
            hair_color: String(a.hair_color || ""),
            hair_style: String(a.hair_style || ""),
            hair_length: String(a.hair_length || ""),
            eye_color: String(a.eye_color || ""),
            skin_tone: String(a.skin_tone || ""),
            body_type: String(a.body_type || ""),
            face_shape: String(a.face_shape || ""),
            style_keywords: Array.isArray(a.style_keywords)
              ? a.style_keywords.join(", ")
              : String(a.style_keywords || ""),
            freeform_notes: String(a.freeform_notes || ""),
          },
          personality: {
            traits: Array.isArray(p.traits) ? p.traits.join(", ") : String(p.traits || ""),
            tone: String(p.tone || ""),
            bio_short: String(p.bio_short || ""),
          },
          boundaries: {
            hard_bans: Array.isArray(b.hard_bans) ? b.hard_bans.join(", ") : "",
            soft_limits: Array.isArray(b.soft_limits) ? b.soft_limits.join(", ") : "",
            content_allowed: Array.isArray(b.content_allowed)
              ? b.content_allowed.join(", ")
              : "",
          },
          speaking_style: {
            formality: String(s.formality || "warm"),
            emoji_use: String(s.emoji_use || "light"),
            example_lines: Array.isArray(s.example_lines)
              ? s.example_lines.join("\n")
              : String(s.example_lines || ""),
          },
        });
      })
      .catch((e) => setError(e.message));
  }, [id, isNew]);

  function payload() {
    return {
      display_name: form.display_name,
      age_appearance_min: Number(form.age_appearance_min),
      age_appearance_band: form.age_appearance_band,
      synthetic_confirmed: form.synthetic_confirmed,
      not_real_person_attested: form.not_real_person_attested,
      attestation_text: form.attestation_text || null,
      niche_tags: splitList(form.niche_tags),
      trigger_word: form.trigger_word || null,
      appearance: {
        ...form.appearance,
        style_keywords: splitList(form.appearance.style_keywords),
      },
      personality: {
        traits: splitList(form.personality.traits),
        tone: form.personality.tone || null,
        bio_short: form.personality.bio_short || null,
      },
      boundaries: {
        hard_bans: splitList(form.boundaries.hard_bans),
        soft_limits: splitList(form.boundaries.soft_limits),
        content_allowed: splitList(form.boundaries.content_allowed),
      },
      speaking_style: {
        formality: form.speaking_style.formality,
        emoji_use: form.speaking_style.emoji_use,
        example_lines: splitList(form.speaking_style.example_lines),
      },
    };
  }

  async function save(e?: FormEvent) {
    e?.preventDefault();
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      if (isNew) {
        const c = await api.createCharacter(payload());
        setCharacter(c);
        setInfo("Character created.");
        nav(`/characters/${c.id}`, { replace: true });
      } else {
        const c = await api.updateCharacter(id!, payload());
        setCharacter(c);
        setInfo("Saved.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function loadPreview() {
    if (!character) return;
    try {
      const p = await api.previewPrompt(character.id, { theme: "portrait" });
      setPreview(p);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function doBootstrap() {
    if (!character) return;
    setBusy(true);
    try {
      await save();
      const r = await api.bootstrap(character.id);
      setCharacter(r.character);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function doLock() {
    if (!character?.current_version) return;
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      const r = await api.lock(character.id, {
        version_id: character.current_version.id,
        checklist_attestation: lockChecks.text,
        confirm_adult: lockChecks.adult,
        confirm_synthetic: lockChecks.synthetic,
        confirm_not_real_person: lockChecks.notReal,
        allow_without_lora: lockChecks.dryRun,
      });
      setCharacter(r.character);
      setInfo("Locked. Status is ready — open Studio and generate with the LoRA.");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-3xl">
            {isNew ? "Create character" : form.display_name || "Edit character"}
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            Guided creator · Flux prompt contract · 21+ synthetic only
            {character && (
              <span className="ml-2 rounded-full bg-white/10 px-2 py-0.5 text-xs capitalize">
                {character.status}
              </span>
            )}
          </p>
        </div>
        {character && (
          <Link to={`/characters/${character.id}/studio`} className="btn-primary">
            Open studio
          </Link>
        )}
      </div>

      <div className="flex flex-wrap gap-2">
        {STEPS.map((s, i) => (
          <button
            key={s}
            type="button"
            onClick={() => setStep(i)}
            className={`rounded-full px-3 py-1 text-xs font-medium ${
              step === i ? "bg-accent text-white" : "bg-white/5 text-slate-400"
            }`}
          >
            {i + 1}. {s}
          </button>
        ))}
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

      <form onSubmit={save} className="card space-y-5 p-6">
        {step === 0 && (
          <>
            <div>
              <label className="label">Display name</label>
              <input
                className="input"
                required
                value={form.display_name}
                onChange={(e) => setForm({ ...form, display_name: e.target.value })}
              />
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className="label">Age appearance band</label>
                <select
                  className="input"
                  value={form.age_appearance_band}
                  onChange={(e) => setForm({ ...form, age_appearance_band: e.target.value })}
                >
                  <option value="mid-20s">Mid-20s</option>
                  <option value="late-20s">Late-20s</option>
                  <option value="30s">30s</option>
                  <option value="40s">40s</option>
                  <option value="50s+">50s+</option>
                </select>
              </div>
              <div>
                <label className="label">Min age appearance (≥21)</label>
                <input
                  type="number"
                  min={21}
                  className="input"
                  value={form.age_appearance_min}
                  onChange={(e) =>
                    setForm({ ...form, age_appearance_min: Number(e.target.value) })
                  }
                />
              </div>
            </div>
            <div>
              <label className="label">Niche tags (comma-separated)</label>
              <input
                className="input"
                value={form.niche_tags}
                onChange={(e) => setForm({ ...form, niche_tags: e.target.value })}
                placeholder="fitness, cozy, lifestyle"
              />
            </div>
            <div>
              <label className="label">LoRA trigger word</label>
              <input
                className="input"
                value={form.trigger_word}
                onChange={(e) => setForm({ ...form, trigger_word: e.target.value })}
                placeholder="auto if blank"
              />
            </div>
          </>
        )}

        {step === 1 && (
          <>
            <div className="grid gap-4 sm:grid-cols-2">
              {(
                [
                  ["hair_color", "Hair color"],
                  ["hair_style", "Hair style"],
                  ["hair_length", "Hair length"],
                  ["eye_color", "Eye color"],
                  ["skin_tone", "Skin tone"],
                  ["body_type", "Body type"],
                  ["face_shape", "Face shape"],
                ] as const
              ).map(([key, label]) => (
                <div key={key}>
                  <label className="label">{label}</label>
                  <input
                    className="input"
                    value={form.appearance[key]}
                    onChange={(e) =>
                      setForm({
                        ...form,
                        appearance: { ...form.appearance, [key]: e.target.value },
                      })
                    }
                  />
                </div>
              ))}
            </div>
            <div>
              <label className="label">Style keywords</label>
              <input
                className="input"
                value={form.appearance.style_keywords}
                onChange={(e) =>
                  setForm({
                    ...form,
                    appearance: { ...form.appearance, style_keywords: e.target.value },
                  })
                }
              />
            </div>
            <div>
              <label className="label">Freeform notes</label>
              <textarea
                className="input min-h-[80px]"
                value={form.appearance.freeform_notes}
                onChange={(e) =>
                  setForm({
                    ...form,
                    appearance: { ...form.appearance, freeform_notes: e.target.value },
                  })
                }
              />
            </div>
            {character && (
              <button type="button" className="btn-ghost" onClick={loadPreview}>
                Preview Flux prompt
              </button>
            )}
            {preview && (
              <div className="space-y-2 rounded-xl bg-black/30 p-4 text-xs">
                <div>
                  <span className="text-emerald-400">Positive</span>
                  <p className="mt-1 text-slate-300">{preview.positive}</p>
                </div>
                <div>
                  <span className="text-rose-400">Negative</span>
                  <p className="mt-1 text-slate-400">{preview.negative}</p>
                </div>
              </div>
            )}
          </>
        )}

        {step === 2 && (
          <>
            <div>
              <label className="label">Traits</label>
              <input
                className="input"
                value={form.personality.traits}
                onChange={(e) =>
                  setForm({
                    ...form,
                    personality: { ...form.personality, traits: e.target.value },
                  })
                }
                placeholder="playful, confident, witty"
              />
            </div>
            <div>
              <label className="label">Tone</label>
              <input
                className="input"
                value={form.personality.tone}
                onChange={(e) =>
                  setForm({
                    ...form,
                    personality: { ...form.personality, tone: e.target.value },
                  })
                }
              />
            </div>
            <div>
              <label className="label">Short bio</label>
              <textarea
                className="input min-h-[80px]"
                value={form.personality.bio_short}
                onChange={(e) =>
                  setForm({
                    ...form,
                    personality: { ...form.personality, bio_short: e.target.value },
                  })
                }
              />
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className="label">Speaking formality</label>
                <select
                  className="input"
                  value={form.speaking_style.formality}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      speaking_style: { ...form.speaking_style, formality: e.target.value },
                    })
                  }
                >
                  <option value="casual">Casual</option>
                  <option value="warm">Warm</option>
                  <option value="playful">Playful</option>
                  <option value="direct">Direct</option>
                </select>
              </div>
              <div>
                <label className="label">Emoji use</label>
                <select
                  className="input"
                  value={form.speaking_style.emoji_use}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      speaking_style: { ...form.speaking_style, emoji_use: e.target.value },
                    })
                  }
                >
                  <option value="none">None</option>
                  <option value="light">Light</option>
                  <option value="heavy">Heavy</option>
                </select>
              </div>
            </div>
            <div>
              <label className="label">Example lines (one per line)</label>
              <textarea
                className="input min-h-[80px]"
                value={form.speaking_style.example_lines}
                onChange={(e) =>
                  setForm({
                    ...form,
                    speaking_style: { ...form.speaking_style, example_lines: e.target.value },
                  })
                }
              />
            </div>
            <p className="text-xs text-slate-500">
              Personality is stored now for future offline captions (post-MVP).
            </p>
          </>
        )}

        {step === 3 && (
          <>
            <div>
              <label className="label">Hard bans → negative prompt</label>
              <textarea
                className="input min-h-[80px]"
                value={form.boundaries.hard_bans}
                onChange={(e) =>
                  setForm({
                    ...form,
                    boundaries: { ...form.boundaries, hard_bans: e.target.value },
                  })
                }
              />
            </div>
            <div>
              <label className="label">Soft limits</label>
              <textarea
                className="input min-h-[60px]"
                value={form.boundaries.soft_limits}
                onChange={(e) =>
                  setForm({
                    ...form,
                    boundaries: { ...form.boundaries, soft_limits: e.target.value },
                  })
                }
              />
            </div>
            <div>
              <label className="label">Content allowed</label>
              <textarea
                className="input min-h-[60px]"
                value={form.boundaries.content_allowed}
                onChange={(e) =>
                  setForm({
                    ...form,
                    boundaries: { ...form.boundaries, content_allowed: e.target.value },
                  })
                }
              />
            </div>
          </>
        )}

        {step === 4 && (
          <>
            <label className="flex items-start gap-3 rounded-xl bg-white/5 p-3 text-sm">
              <input
                type="checkbox"
                checked={form.synthetic_confirmed}
                onChange={(e) => setForm({ ...form, synthetic_confirmed: e.target.checked })}
                className="mt-1"
              />
              <span>
                I confirm this persona is <strong>fully synthetic</strong> (AI-generated identity).
              </span>
            </label>
            <label className="flex items-start gap-3 rounded-xl bg-white/5 p-3 text-sm">
              <input
                type="checkbox"
                checked={form.not_real_person_attested}
                onChange={(e) =>
                  setForm({ ...form, not_real_person_attested: e.target.checked })
                }
                className="mt-1"
              />
              <span>
                I attest this is <strong>not intended to recreate a real person</strong>. Lookalike
                prevention is policy/UX, not automatic detection.
              </span>
            </label>
            <div>
              <label className="label">Attestation notes</label>
              <textarea
                className="input min-h-[60px]"
                value={form.attestation_text}
                onChange={(e) => setForm({ ...form, attestation_text: e.target.value })}
              />
            </div>

            {character && (
              <div className="space-y-3 border-t border-white/10 pt-4">
                <h3 className="text-sm font-semibold text-slate-200">Lifecycle actions</h3>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    className="btn-ghost"
                    disabled={busy || character.status === "ready"}
                    onClick={doBootstrap}
                  >
                    Mark bootstrap
                  </button>
                </div>
                <p className="text-xs text-slate-500">
                  Bootstrap unlocks seed gallery & still batches (Unlocked banner). Production lock
                  requires a registered LoRA file unless you explicitly dry-run.
                </p>
                {!hasLora && (
                  <p className="text-xs text-amber-200">
                    No LoRA file on this version yet — register weights in Studio, or check dry-run
                    below (identity will drift).
                  </p>
                )}
                <div className="space-y-2 rounded-xl border border-white/10 p-3">
                  <label className="flex gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={lockChecks.adult}
                      onChange={(e) => setLockChecks({ ...lockChecks, adult: e.target.checked })}
                    />
                    Clearly adult 21+ appearance
                  </label>
                  <label className="flex gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={lockChecks.synthetic}
                      onChange={(e) =>
                        setLockChecks({ ...lockChecks, synthetic: e.target.checked })
                      }
                    />
                    Synthetic identity confirmed
                  </label>
                  <label className="flex gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={lockChecks.notReal}
                      onChange={(e) => setLockChecks({ ...lockChecks, notReal: e.target.checked })}
                    />
                    Not targeting a real person
                  </label>
                  <label className="label mt-2">Lock notes (required, 10+ characters)</label>
                  <textarea
                    className="input min-h-[60px]"
                    placeholder="e.g. I confirm Ruby is a synthetic adult 21+ persona, not a real person."
                    value={lockChecks.text}
                    onChange={(e) => setLockChecks({ ...lockChecks, text: e.target.value })}
                  />
                  <label className="flex gap-2 text-sm text-amber-200/90">
                    <input
                      type="checkbox"
                      checked={lockChecks.dryRun}
                      onChange={(e) => setLockChecks({ ...lockChecks, dryRun: e.target.checked })}
                    />
                    Dry-run lock without LoRA (not for production)
                  </label>
                  {character.status === "ready" && (
                    <p className="text-sm text-emerald-300">
                      Already locked (ready). Use{" "}
                      <Link to={`/characters/${character.id}/studio`} className="underline">
                        Open studio
                      </Link>{" "}
                      to generate with the LoRA.
                    </p>
                  )}
                  <button
                    type="button"
                    className="btn-primary"
                    disabled={
                      busy ||
                      (!hasLora && !lockChecks.dryRun) ||
                      lockChecks.text.trim().length < 10 ||
                      !lockChecks.adult ||
                      !lockChecks.synthetic ||
                      !lockChecks.notReal
                    }
                    onClick={doLock}
                  >
                    {character.status === "ready" ? "Re-lock (already ready)" : "Human lock → ready"}
                  </button>
                </div>
              </div>
            )}
          </>
        )}

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-white/10 pt-4">
          <button
            type="button"
            className="btn-ghost"
            disabled={step === 0}
            onClick={() => setStep((s) => Math.max(0, s - 1))}
          >
            Back
          </button>
          <div className="flex gap-2">
            <button type="submit" className="btn-primary" disabled={busy}>
              {isNew ? "Create" : "Save"}
            </button>
            {step < STEPS.length - 1 && (
              <button
                type="button"
                className="btn-ghost"
                onClick={() => setStep((s) => Math.min(STEPS.length - 1, s + 1))}
              >
                Next
              </button>
            )}
          </div>
        </div>
      </form>
    </div>
  );
}

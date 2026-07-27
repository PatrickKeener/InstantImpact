# Safety & compliance

InstantImpact is for **synthetic adult (21+) personas** only.

## Hard rules

1. **Age appearance ≥ 21** — schema enforced; underage language hard-denied.
2. **Synthetic only** — confirmation required before generation.
3. **No real-person recreation tooling** — MVP is **generate-only refs** (no external photo upload).
4. **Lookalike prevention** is **policy + UX**, not guaranteed automated detection.
5. **Disclosure** travels with exports (`*.disclosure.json` sidecars + manifest).

## Human gates

- Character **lock** requires checklist (adult, synthetic, not real person).
- Export of approved sets requires human export approval (PR-10).

## Deny categories

See `instantimpact_common.safety_lists.DENY_CATEGORIES` — enforced on every enqueue path via `validate_for_enqueue`.

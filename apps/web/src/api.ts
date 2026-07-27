const BASE = "";

/** Optional LAN auth — set VITE_API_TOKEN at build/dev time or localStorage key instantimpact_api_token */
function apiToken(): string {
  try {
    return (
      (import.meta as ImportMeta & { env?: { VITE_API_TOKEN?: string } }).env
        ?.VITE_API_TOKEN ||
      localStorage.getItem("instantimpact_api_token") ||
      ""
    );
  } catch {
    return "";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init?.headers as Record<string, string> | undefined),
  };
  const token = apiToken();
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || JSON.stringify(body);
    } catch {
      /* ignore */
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.json() as Promise<T>;
}

export type Character = {
  id: string;
  slug: string;
  display_name: string;
  status: string;
  preferred_pipeline: string;
  age_appearance_min: number;
  age_appearance_band: string;
  synthetic_confirmed: boolean;
  not_real_person_attested: boolean;
  attestation_text: string | null;
  locked_version_id: string | null;
  retrain_version_id: string | null;
  niche_tags: string[];
  created_at: string;
  updated_at: string;
  current_version: {
    id: string;
    version_int: number;
    status: string;
    appearance: Record<string, unknown>;
    personality: Record<string, unknown>;
    boundaries: Record<string, unknown>;
    speaking_style: Record<string, unknown>;
    trigger_word: string | null;
    prompt_contract: Record<string, unknown>;
    pipeline_params: Record<string, unknown>;
  } | null;
};

export type Job = {
  id: string;
  type: string;
  status: string;
  character_id: string | null;
  items: {
    id: string;
    item_index: number;
    status: string;
    asset_id: string | null;
    consistency_score: number | null;
  }[];
  error_message: string | null;
  created_at: string;
};

export type Asset = {
  id: string;
  path: string;
  thumb_path: string | null;
  decision: string;
  seed: number | null;
  prompt_positive: string | null;
  consistency_score: number | null;
  created_at: string;
};

export const api = {
  health: () => request<{ status: string; mvp: Record<string, unknown> }>("/api/system/health"),
  listCharacters: () => request<Character[]>("/api/characters"),
  getCharacter: (id: string) => request<Character>(`/api/characters/${id}`),
  createCharacter: (body: unknown) =>
    request<Character>("/api/characters", { method: "POST", body: JSON.stringify(body) }),
  updateCharacter: (id: string, body: unknown) =>
    request<Character>(`/api/characters/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  bootstrap: (id: string) =>
    request<{ character: Character; message: string }>(`/api/characters/${id}/bootstrap`, {
      method: "POST",
    }),
  lock: (id: string, body: unknown) =>
    request<{ character: Character; message: string }>(`/api/characters/${id}/lock`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  previewPrompt: (id: string, body: unknown) =>
    request<{ positive: string; negative: string }>(`/api/characters/${id}/preview-prompt`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  seedGallery: (id: string, body: unknown) =>
    request<Job>(`/api/characters/${id}/seed-gallery`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  stillBatch: (id: string, body: unknown) =>
    request<Job>(`/api/characters/${id}/still-batch`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  listJobs: (characterId?: string) =>
    request<Job[]>(`/api/jobs${characterId ? `?character_id=${characterId}` : ""}`),
  getJob: (id: string) => request<Job>(`/api/jobs/${id}`),
  listAssets: (characterId: string) =>
    request<Asset[]>(`/api/characters/${characterId}/assets`),
  setDecision: (assetId: string, decision: string) =>
    request(`/api/assets/${assetId}/decision`, {
      method: "POST",
      body: JSON.stringify({ decision }),
    }),
  mediaUrl: (relPath: string) => {
    const url = `/api/system/media/${relPath}`;
    // img tags cannot set Authorization; if token required, use query (dev only) or same-origin session later
    const token = apiToken();
    if (token) return `${url}?token=${encodeURIComponent(token)}`;
    return url;
  },
  gpu: () =>
    request<{ mock_generation: boolean; message: string; comfy_enabled: boolean }>(
      "/api/system/gpu"
    ),
};

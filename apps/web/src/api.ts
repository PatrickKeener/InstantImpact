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
    lora_path?: string | null;
    prompt_contract: Record<string, unknown>;
    pipeline_params: Record<string, unknown>;
  } | null;
};

export type LoraStatus = {
  character_id: string;
  status: string;
  approved_stills: number;
  dataset_images: number;
  trigger_word: string | null;
  lora_path: string | null;
  lora_file_present: boolean | null;
  comfy_lora_name: string | null;
  version_id: string | null;
  version_int: number | null;
  ready_for_dataset: boolean;
  recommended_min: number;
  warning?: string | null;
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
  createRandomCharacter: (body?: {
    seed?: number;
    auto_attest?: boolean;
    auto_bootstrap?: boolean;
  }) =>
    request<Character>("/api/characters/random", {
      method: "POST",
      body: JSON.stringify(body || {}),
    }),
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
  loraStatus: (id: string) => request<LoraStatus>(`/api/characters/${id}/lora/status`),
  buildDataset: (id: string, body?: { decision?: string; min_images?: number }) =>
    request<{
      character: Character;
      dataset_dir: string;
      trigger_word: string;
      image_count: number;
      warning: string | null;
      train_config: Record<string, unknown>;
      lora_dir: string;
    }>(`/api/characters/${id}/dataset/build`, {
      method: "POST",
      body: JSON.stringify(body || {}),
    }),
  registerLora: (
    id: string,
    body: { source_path: string; strength?: number; install_to_comfy?: boolean }
  ) =>
    request<{
      character: Character;
      comfy_lora_name: string;
      trigger_word: string;
      message: string;
      lora_path: string;
    }>(`/api/characters/${id}/lora/register`, {
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
  deleteAsset: (assetId: string, deleteFiles = true) =>
    request<{ id: string; deleted: boolean; character_id: string; files_removed: number }>(
      `/api/assets/${assetId}?delete_files=${deleteFiles ? "true" : "false"}`,
      { method: "DELETE" }
    ),
  bulkDeleteAssets: (
    characterId: string,
    body: { asset_ids?: string[]; decision?: string; delete_files?: boolean }
  ) =>
    request<{ character_id: string; deleted: number; files_removed: number }>(
      `/api/characters/${characterId}/assets/delete`,
      { method: "POST", body: JSON.stringify(body) }
    ),
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

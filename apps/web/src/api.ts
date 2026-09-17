const BASE = "";

/** Optional LAN auth — set VITE_API_TOKEN at build/dev time or localStorage key instantimpact_api_token */
export function apiToken(): string {
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

export function setApiToken(token: string) {
  localStorage.setItem("instantimpact_api_token", token);
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
    const msg = typeof detail === "string" ? detail : JSON.stringify(detail);
    throw new Error(`${res.status} ${msg} (${path})`);
  }
  if (res.status === 204) return undefined as T;
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
  preview_thumb?: string | null;
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
  coverage?: Record<string, boolean>;
  coverage_missing?: string[];
  toolkit_ready?: boolean;
};

export type Job = {
  id: string;
  type: string;
  status: string;
  character_id: string | null;
  cancel_requested?: boolean;
  error_message: string | null;
  created_at: string;
  items: {
    id: string;
    item_index: number;
    status: string;
    asset_id: string | null;
    consistency_score: number | null;
  }[];
};

export type Asset = {
  id: string;
  path: string;
  thumb_path: string | null;
  decision: string;
  seed: number | null;
  prompt_positive: string | null;
  prompt_negative?: string | null;
  consistency_score: number | null;
  created_at: string;
  width?: number | null;
  height?: number | null;
};

export type ApprovedSet = {
  id: string;
  character_id: string;
  title: string;
  manifest_path: string | null;
  export_path: string | null;
  human_export_approved_at: string | null;
  created_at: string;
  item_count: number;
  download?: string;
};

export type Health = {
  status: string;
  mvp?: Record<string, unknown>;
  redis_ok?: boolean;
  comfy_healthy?: boolean | null;
  comfy_enabled?: boolean;
  gpu_locked?: boolean;
  disk_free_gb?: number | null;
  auth_required?: boolean;
  mock_generation?: boolean;
};

export type GpuStatus = {
  locked: boolean;
  holder_job_id: string | null;
  message: string;
  mock_generation: boolean;
  comfy_enabled: boolean;
  comfy_healthy: boolean | null;
  redis_ok: boolean | null;
};

export const api = {
  health: () => request<Health>("/api/system/health"),
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
  regenerate: (characterId: string, assetId: string, count = 1) =>
    request<Job>(`/api/characters/${characterId}/assets/${assetId}/regenerate`, {
      method: "POST",
      body: JSON.stringify({ count }),
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
  trainLora: (
    id: string,
    body?: { steps?: number; strength?: number; min_images?: number; rebuild_dataset?: boolean }
  ) =>
    request<Job>(`/api/characters/${id}/lora/train`, {
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
  cancelJob: (id: string) => request<Job>(`/api/jobs/${id}/cancel`, { method: "POST" }),
  listAssets: (characterId: string, decision?: string) =>
    request<Asset[]>(
      `/api/characters/${characterId}/assets${decision ? `?decision=${decision}` : ""}`
    ),
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
  listApprovedSets: (characterId: string) =>
    request<ApprovedSet[]>(`/api/characters/${characterId}/approved-sets`),
  createApprovedSet: (characterId: string, body: { title: string; asset_ids: string[] }) =>
    request<ApprovedSet>(`/api/characters/${characterId}/approved-sets`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  exportApprovedSet: (setId: string, confirm = true) =>
    request<ApprovedSet>(`/api/approved-sets/${setId}/export`, {
      method: "POST",
      body: JSON.stringify({ confirm_adult_synthetic: confirm }),
    }),
  mediaUrl: (relPath: string) => {
    const url = `/api/system/media/${relPath}`;
    const token = apiToken();
    if (token) return `${url}?token=${encodeURIComponent(token)}`;
    return url;
  },
  gpu: () => request<GpuStatus>("/api/system/gpu"),
};

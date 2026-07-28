#!/usr/bin/env bash
# Print dataset paths + AI Toolkit hints after "Build training set" in the studio.
# Usage: ./scripts/nemesis/train_lora_hint.sh <character_id>
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CID="${1:-}"
if [[ -z "$CID" ]]; then
  echo "Usage: $0 <character_id>"
  echo "  character_id is the UUID from the studio URL / API"
  exit 1
fi

# Find version folders with a train_config
mapfile -t CFGS < <(find "${ROOT}/data/characters/${CID}" -name train_config.json 2>/dev/null | sort)
if [[ ${#CFGS[@]} -eq 0 ]]; then
  echo "No train_config.json under data/characters/${CID}"
  echo "In the UI: approve stills → Build training set from approved"
  exit 1
fi

CFG="${CFGS[-1]}"
echo "== Latest train_config =="
echo "  $CFG"
echo ""
python3 - <<PY
import json
from pathlib import Path
cfg = json.loads(Path("${CFG}").read_text())
print("trigger_word:", cfg.get("trigger_word"))
print("dataset_dir: ", cfg.get("dataset_dir"))
print("output_dir:  ", cfg.get("output_dir"))
print("images:      ", cfg.get("image_count"))
print("steps hint:  ", cfg.get("steps_suggested"))
print("network:     ", cfg.get("network"))
print()
print("Next steps:")
print("  1) Stop vLLM / free GPU: docker stop vllm")
print("  2) Train a Flux LoRA with Ostris AI Toolkit (or compatible) using dataset_dir above.")
print("     Use trigger_word in every caption (already written as .txt next to images).")
print("  3) Copy output to:  {output_dir}/model.safetensors")
print("  4) In InstantImpact studio → Register LoRA → path to that file")
print("  5) Restart Comfy if it was running so it rescans models/loras")
print("  6) Lock character → generate batches (worker uses flux_still_character_lora_v1)")
PY

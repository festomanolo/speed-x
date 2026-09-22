"""Download aac6fef/laya-multilingual-coreml reliably using huggingface_hub."""

import os
from pathlib import Path
from huggingface_hub import snapshot_download

MODEL_ID = "aac6fef/laya-multilingual-coreml"
TARGET_DIR = Path(__file__).resolve().parent.parent / "models" / "laya-multilingual"

print(f"Downloading {MODEL_ID} to {TARGET_DIR}...")
TARGET_DIR.mkdir(parents=True, exist_ok=True)

path = snapshot_download(
    repo_id=MODEL_ID,
    local_dir=str(TARGET_DIR),
    max_workers=4,
)
print(f"Successfully downloaded to {path}")

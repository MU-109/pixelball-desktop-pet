"""Manually download faster-whisper model to project directory (using HuggingFace mirror)

Usage: Run in project .venv
    .venv\Scripts\python download_model.py [tiny|base|small]

Default downloads base model (~150MB), requires network connection.
"""

import os
import sys

# Force use of domestic mirror
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

# Cache model in project directory
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_CACHE = os.path.join(PROJECT_DIR, "stt_models")
os.environ["HF_HOME"] = MODEL_CACHE
os.environ["HUGGINGFACE_HUB_CACHE"] = os.path.join(MODEL_CACHE, "hub")
os.makedirs(MODEL_CACHE, exist_ok=True)

MODEL_SIZE = sys.argv[1] if len(sys.argv) > 1 else "base"
MODEL_ID = f"Systran/faster-whisper-{MODEL_SIZE}"

print(f"Model ID: {MODEL_ID}")
print(f"Cache dir: {MODEL_CACHE}")
print(f"Mirror: {os.environ['HF_ENDPOINT']}")
print()

try:
    from huggingface_hub import snapshot_download

    print(f"Start downloading {MODEL_SIZE} model...")
    local_path = snapshot_download(
        repo_id=MODEL_ID,
        cache_dir=os.path.join(MODEL_CACHE, "hub"),
        resume_download=True,
        max_workers=4,
    )
    print(f"Download complete: {local_path}")

    # Verify
    from faster_whisper import WhisperModel
    print("Loading model for verification...")
    model = WhisperModel(
        MODEL_SIZE,
        device="cpu",
        compute_type="int8",
    )
    print("Model loaded successfully! Speech-to-text is ready.")

except Exception as e:
    print(f"Download failed: {e}")
    print()
    print("Manual download steps:")
    print(f"1. Open in browser: https://hf-mirror.com/{MODEL_ID}/tree/main")
    print(f"2. Download all files to: {MODEL_CACHE}")
    print("3. Re-run this script to verify")
    sys.exit(1)

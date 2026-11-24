"""Download the embedding model files into the configured cache WITHOUT loading the model into memory.

Run during the cloud *build* step so the first user request does not have to download ~90 MB:

    python scripts/prefetch_model.py            # failure is only a warning (the app downloads on first use)
    python scripts/prefetch_model.py --strict   # exit status 1 on failure

It reads EMBEDDING_MODEL and MODEL_CACHE_DIR from the same settings the app uses, so the cache location
at build time and at runtime are identical. Loading into memory still happens lazily at the first
recommendation request (or at startup if PRELOAD_MODEL=true).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Files the CPU/PyTorch loader does not need (alternative weight formats are large).
IGNORE = ["*.h5", "*.ot", "*.msgpack", "onnx/*", "openvino/*"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--strict", action="store_true", help="exit with status 1 if the download fails")
    args = ap.parse_args(argv)

    from app.core.config import get_settings
    s = get_settings()
    cache = s.model_cache_path
    print(f"Prefetching '{s.embedding_model}' into {cache or 'the default Hugging Face cache'}", flush=True)
    try:
        from huggingface_hub import snapshot_download
        path = snapshot_download(repo_id=s.embedding_model, cache_dir=str(cache) if cache else None, ignore_patterns=IGNORE)
    except Exception as exc:  # noqa: BLE001 - any failure (network, auth, missing package) is non-fatal by default
        print(f"WARNING: could not prefetch the model ({type(exc).__name__}). "
              "The app will download it on first use instead.", file=sys.stderr)
        return 1 if args.strict else 0
    print(f"Model files are in {path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

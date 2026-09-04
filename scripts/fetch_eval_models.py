#!/usr/bin/env python3
"""Fetch a sentence-transformers model directory for the eval Docker image.

Why not `git clone https://huggingface.co/...`? The HF hub repo for
all-mpnet-base-v2 contains multi-gigabyte ONNX/OpenVINO artifacts that the
runtime never needs. This script downloads only the files sentence-transformers
actually loads (pytorch weights + tokenizer + configs), with a mirror fallback
chain: huggingface.co -> hf-mirror.com.

Used at docker build time (see Dockerfile); runnable locally too:

    python scripts/fetch_eval_models.py \
        --repo sentence-transformers/all-mpnet-base-v2 \
        --dest /models/all-mpnet-base-v2

No credentials, no secrets, stdlib only.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request

# sentence-transformers bi-encoder (has Pooling/modules layout)
REQUIRED_ST = {
    "config.json",
    "config_sentence_transformers.json",
    "modules.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "vocab.txt",
    "model.safetensors",
    "1_Pooling/config.json",
}
# cross-encoder (e.g. ms-marco-MiniLM-L-6-v2): no modules/Pooling layout
REQUIRED_CE = {
    "config.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "vocab.txt",
    "model.safetensors",
}
_UA = {"User-Agent": "minta-eval-build/1.0 (fetch_eval_models)"}
MIRRORS = ["https://huggingface.co", "https://hf-mirror.com"]
_EXCLUDED_SUFFIXES = (".onnx", ".bin", ".msgpack", ".h5",
                      ".gitattributes", "README.md")
_TIMEOUT = 8  # main hub may be unreachable (CN networks) -> fail fast to mirror


def _endpoints() -> list[str]:
    env_endpoint = os.environ.get("HF_ENDPOINT", "").rstrip("/")
    return [env_endpoint] if env_endpoint else MIRRORS


def resolve_repo_files(repo: str, api_root: str) -> list[str]:
    url = f"{api_root}/api/models/{repo}"
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        meta = json.loads(resp.read().decode("utf-8"))
    return [s["rfilename"] for s in meta.get("siblings", [])]


def fetch(repo: str, dest: str, only_check: bool = False,
          kind: str = "st") -> None:
    os.makedirs(dest, exist_ok=True)
    required = REQUIRED_ST if kind == "st" else REQUIRED_CE
    files: list[str] | None = None
    for mirror in _endpoints():
        try:
            files = resolve_repo_files(repo, mirror)
            break
        except Exception as exc:
            print(f"  ! api list failed on {mirror}: {exc}", flush=True)
    if files is None:
        raise SystemExit("could not resolve model file list on any mirror")

    missing = required - set(files)
    if missing:
        raise SystemExit(f"repo {repo} lacks required files: {missing}")
    if only_check:
        print(f"model list OK on {mirror if files else 'endpoint'}: "
              f"{len(files)} files, required present", flush=True)
        return

    wanted = sorted(
        f for f in files
        if f in required
        or (f.startswith("1_Pooling/") and f.endswith(".json"))
        or (f.startswith("tokenizer/"))
        or (f == "pytorch_model.bin" and "model.safetensors" not in files))
    for f in wanted:
        if f.endswith(_EXCLUDED_SUFFIXES) and f not in required:
            continue
        target = os.path.join(dest, f)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        if os.path.exists(target) and os.path.getsize(target) > 0:
            print(f"  exists {f}", flush=True)
            continue
        ok = False
        for mirror in _endpoints():
            url = f"{mirror}/{repo}/resolve/main/{f}"
            req = urllib.request.Request(url, headers=_UA)
            try:
                print(f"  fetch {url}", flush=True)
                with urllib.request.urlopen(req, timeout=120) as resp, \
                        open(target, "wb") as out:
                    out.write(resp.read())
                ok = True
                break
            except Exception as exc:
                print(f"  ! failed {mirror}: {exc}", flush=True)
        if not ok:
            raise SystemExit(f"download failed: {f}")

    missing = [f for f in required if not os.path.exists(os.path.join(dest, f))]
    if missing:
        raise SystemExit(f"missing required files after fetch: {missing}")
    print(f"model ready at {dest}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", default="sentence-transformers/all-mpnet-base-v2")
    ap.add_argument("--dest", required=True)
    ap.add_argument("--only-check", action="store_true",
                    help="verify the file list without downloading")
    ap.add_argument("--kind", choices=("st", "ce"), default="st",
                    help="st = sentence-transformers bi-encoder (default), "
                         "ce = cross-encoder (ms-marco reranker, no Pooling)")
    args = ap.parse_args()
    fetch(args.repo, args.dest, only_check=args.only_check, kind=args.kind)


if __name__ == "__main__":
    main()

"""Proxy evaluation on the OFFICIAL LoCoMo-Refined public split.

This is the closest available replay of the AML LoCoMo-Refined track: the
dataset itself ships platform-shaped files (conversations.jsonl with
session dates and message roles + questions.jsonl with evidence). We:

  * filter to the purely textual questions (is_multi_modality=false), because
    the Add contract carries text only and the textual track is the target;
  * chunk sessions by the platform rule (<=20 messages / <=2000 words);
  * synthesize per-message timestamps from the session date_time + ordinal
    minute (LoCoMo turns carry no clock time);
  * score with the official AML locomo-refined templates (DeepSeek as the
    local judge — arm-to-arm comparisons only).

Usage (unzip the official repo to a local dir first):
    D:/pycharm/anaconda/python.exe docs/eval-proxy/proxy_refined.py \
        --data D:/LoCoMo_refined-main/data/public --max-convs 3
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone

if sys.stdout.encoding and "utf-8" not in sys.stdout.encoding.lower():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
_SERVER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "server")
if _SERVER not in sys.path:
    sys.path.insert(0, _SERVER)

import httpx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from eval_store import mem_id  # noqa: E402
from eval_app import create_eval_app  # noqa: E402

from proxy_eval import (  # noqa: E402
    parse_judge_label, llm_complete, render_answer_prompt, render_judge_prompt,
)

CHUNK_MAX_MESSAGES = 20
CHUNK_MAX_WORDS = 2000
_date_formats = [
    "%I:%M %p on %d %B %Y",
    "%I:%M %p on %d %B, %Y",
    "%I:%M %p on %d %B %Y",
    "%I:%M%p on %d %B, %Y",
]


def parse_session_date(s: str):
    s = re.sub(r"\s+", " ", s.strip().replace("Sept ", "Sep ").replace(".", ""))
    for fmt in _date_formats:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def epoch_ms(dt: datetime) -> int:
    return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)


def _words(msgs: list[dict]) -> int:
    return sum(len(str(m.get("text", "")).split()) for m in msgs)


def chunk_messages(msgs: list[dict]) -> list[list[dict]]:
    chunks: list[list[dict]] = [[]]
    for m in msgs:
        if len(chunks[-1]) >= CHUNK_MAX_MESSAGES or _words(chunks[-1]) + _words([m]) > CHUNK_MAX_WORDS:
            chunks.append([])
        chunks[-1].append(m)
    return [c for c in chunks if c]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", default=r"D:\LoCoMo_refined-main\data\public")
    ap.add_argument("--max-convs", type=int, default=10)
    ap.add_argument("--max-questions", type=int, default=0)  # 0 = all textual
    ap.add_argument("--top-k", type=int, default=100)
    ap.add_argument("--outdir", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "runs", "refined"))
    args = ap.parse_args()

    base_url = os.environ.get("PROXY_LLM_BASE", "")
    api_key = os.environ.get("PROXY_LLM_KEY", "")
    model = os.environ.get("PROXY_LLM_MODEL", "gpt-4o-mini")
    if not (base_url and api_key) and os.environ.get("DEEPSEEK_API_KEY"):
        base_url = base_url or "https://api.deepseek.com/v1"
        api_key = os.environ["DEEPSEEK_API_KEY"]
        model = os.environ.get("PROXY_LLM_MODEL", "deepseek-chat")
    assert base_url and api_key, "no LLM credentials (PROXY_LLM_* or DEEPSEEK_API_KEY)"

    os.makedirs(args.outdir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    outdir = os.path.join(args.outdir, stamp)
    os.makedirs(outdir, exist_ok=True)
    db_url = f"sqlite:///{(os.path.join(outdir, 'proxy.db')).replace(os.sep, '/')}"
    if os.path.isdir(r"D:\all-mpnet-base-v2"):
        os.environ.setdefault("MINTA_EVAL_EMBED_MODEL", r"D:\all-mpnet-base-v2")

    conv_path = os.path.join(args.data, "conversations.jsonl")
    q_path = os.path.join(args.data, "questions.jsonl")
    convs = [json.loads(l) for l in open(conv_path, encoding="utf-8") if l.strip()][:args.max_convs]
    all_q = [json.loads(l) for l in open(q_path, encoding="utf-8") if l.strip()]
    qs = [q for q in all_q if str(q.get("is_multi_modality", "false")).lower() == "false"
          and q["sample_id"] in {c["sample_id"] for c in convs}]
    if args.max_questions > 0:
        qs = qs[: args.max_questions]
    print(f"convs={len(convs)} textual_questions={len(qs)} (of {len(all_q)})")

    app = create_eval_app(db_url=db_url)
    t0 = time.time()
    with TestClient(app) as client:
        items = []
        for conv in convs:
            sample = conv["sample_id"]
            dia_map = {}
            chunk_no = 0
            for sess in conv["sessions"]:
                dt = parse_session_date(sess.get("date_time", "")) or datetime(2023, 1, 1)
                turns = []
                for i, m in enumerate(sess["messages"]):
                    turns.append({
                        "role": m.get("role") or ("user" if m.get("speaker") == conv.get("speaker_a") else "assistant"),
                        "content": m.get("text") or m.get("blip_caption") or "[image]",
                        "timestamp": epoch_ms(dt) + i * 60_000,
                        "dia_id": m.get("dia_id", f"{sess['session_index']}:{i}"),
                    })
                for chunk in chunk_messages(turns):
                    req_id = f"prf:{sample}:{chunk_no}"
                    r = client.post("/add", json={
                        "request_id": req_id, "user_id": f"prf:{sample}",
                        "session_id": f"prf:{sample}:s{sess['session_index']}",
                        "messages": [{"role": m["role"], "content": m["content"],
                                      "timestamp": m["timestamp"]} for m in chunk]})
                    assert r.status_code == 200, (req_id, r.text)
                    for j, m in enumerate(chunk):
                        dia_map[m["dia_id"]] = (f"prf:{sample}", req_id, j)
                    chunk_no += 1
            for q in [q for q in qs if q["sample_id"] == sample]:
                r = client.post("/search", json={
                    "query": q["question"], "user_id": f"prf:{sample}", "top_k": args.top_k})
                hits = r.json()["data"]
                ev = [dia_map[e] for e in q.get("evidence", []) if e in dia_map]
                cov = 0.0
                if ev:
                    ids = {h["id"] for h in hits}
                    cov = sum(1 for _, req, idx in ev if mem_id(req, idx) in ids) / len(ev)
                items.append({
                    "id": q["qa_id"], "question": q["question"],
                    "gold": " ; ".join(q.get("answer", [])),
                    "category": str(q.get("category", "?")),
                    "retrieved": [h["content"] for h in hits],
                    "coverage@k": round(cov, 3),
                })
    print(f"ingest+retrieval {time.time()-t0:.0f}s — {len(items)} items, "
          f"mean coverage@{args.top_k} = {sum(i['coverage@k'] for i in items)/len(items):.3f}")

    client = httpx.Client()
    results = []
    for i, item in enumerate(items):
        gen = llm_complete(client, base_url, api_key, model,
                           render_answer_prompt(item["question"], item["retrieved"]))
        judge = llm_complete(client, base_url, api_key, model,
                             render_judge_prompt(item["question"], item["gold"], gen))
        label = parse_judge_label(judge)
        results.append({**item, "label": label, "is_correct": label == "CORRECT"})
        if (i + 1) % 100 == 0:
            print(f"  {i+1}/{len(items)} judged — "
                  f"acc={sum(r['is_correct'] for r in results)/len(results):.3f}", flush=True)
    client.close()

    by_cat = defaultdict(list)
    for r in results:
        by_cat[r["category"]].append(r["is_correct"])
    overall = sum(r["is_correct"] for r in results) / len(results)
    print(f"\n=== refined proxy accuracy: {overall:.3f} ({int(sum(r['is_correct'] for r in results))}/{len(results)}) ===")
    for c, vals in sorted(by_cat.items()):
        print(f"  cat {c}: {sum(vals)/len(vals):.3f} (n={len(vals)})")
    with open(os.path.join(outdir, "items.jsonl"), "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(os.path.join(outdir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump({"overall": overall,
                   "by_category": {c: sum(v)/len(v) for c, v in by_cat.items()},
                   "mean_coverage": sum(i["coverage@k"] for i in results)/len(results),
                   "n": len(results)}, f, ensure_ascii=False, indent=2)
    print("saved ->", outdir)


if __name__ == "__main__":
    main()

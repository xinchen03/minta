"""CLBench / CLBench-Life rehearsal: giant-document in-context QA + rubric judge.

Pit-hunting goals:
  * single documents up to ~180k chars (20k+ words) — the platform splits at
    sentence boundaries, which our replay must simulate (message-level
    chunking alone would blow the 2000-word budget);
  * questions demand EXACT entity references (hand numbers, card names,
    method terms) from specific doc regions — the hypothesis to test: does a
    lexical BM25 channel help where dense embeddings are weak on precise ids?
    (MINTA_EVAL_BM25=1 arm);
  * judging is rubric-based (each rubric a binary criterion) — one aggregated
    rubric-judge call per sample keeps LLM cost low.

Data: D:/浏览器下载/CL-bench.jsonl (2242) and CL-bench%20Life.jsonl (405);
schema {messages[], rubrics[], metadata{}}. Memory = messages[:-1], query =
final user message, system persona messages excluded (same discipline as the
PersonaMem rehearsal).

Usage:
    D:/pycharm/anaconda/python.exe docs/eval-proxy/proxy_clbench.py \
        --data "D:/浏览器下载/CL-bench.jsonl" --max-samples 40
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

_SERVER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "server")
if _SERVER not in sys.path:
    sys.path.insert(0, _SERVER)

import httpx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from eval_app import create_eval_app  # noqa: E402
from proxy_eval import llm_complete  # noqa: E402

MAX_MSG_WORDS = 2000
MAX_REQ_MSGS = 20


def split_long_content(text: str, max_words: int = MAX_MSG_WORDS) -> list[str]:
    """Split one very long message at sentence boundaries (platform rule)."""
    if len(text.split()) <= max_words:
        return [text]
    sentences = re.split(r"(?<=[.!?])\s+|\n+", text)
    pieces, cur = [], []
    for s in sentences:
        s = s.strip()
        if not s:
            continue
        if len(" ".join(cur).split()) + len(s.split()) > max_words and cur:
            pieces.append(" ".join(cur)); cur = []
        cur.append(s)
    if cur:
        pieces.append(" ".join(cur))
    return pieces


def chunk_requests(messages: list[dict]) -> list[list[dict]]:
    chunks, cur = [], []
    for m in messages:
        if len(cur) >= MAX_REQ_MSGS:
            chunks.append(cur); cur = []
        cur.append(m)
    if cur:
        chunks.append(cur)
    return chunks


def rubric_judge_prompt(question: str, answer: str, rubrics: list[str]) -> str:
    items = "\n".join(f"{i}. {r}" for i, r in enumerate(rubrics))
    return (
        "Judge whether the answer satisfies each criterion. Reply with a JSON "
        f"array of {{'index': i, 'pass': true|false}} for ALL criteria.\n\n"
        f"Question: {question}\n\nAnswer: {answer}\n\nCriteria:\n{items}\n\n"
        "JSON array only:"
    )


def parse_rubric_flags(text: str, n: int) -> list[bool]:
    m = re.search(r"\[.*\]", text or "", re.S)
    if not m:
        return [False] * n
    try:
        arr = json.loads(m.group(0).replace("'", '"'))
        flags = [False] * n
        for it in arr:
            if isinstance(it, dict) and "index" in it:
                i = int(it["index"])
                if 0 <= i < n:
                    flags[i] = bool(it.get("pass", False))
        return flags
    except Exception:
        return [False] * n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=r"D:\浏览器下载\CL-bench.jsonl")
    ap.add_argument("--max-samples", type=int, default=40)
    ap.add_argument("--top-k", type=int, default=100)
    ap.add_argument("--outdir", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "runs", "clbench"))
    args = ap.parse_args()

    base_url = os.environ.get("PROXY_LLM_BASE", "")
    api_key = os.environ.get("PROXY_LLM_KEY", "")
    model = os.environ.get("PROXY_LLM_MODEL", "gpt-4o-mini")
    if not (base_url and api_key) and os.environ.get("DEEPSEEK_API_KEY"):
        base_url = base_url or "https://api.deepseek.com/v1"
        api_key = os.environ["DEEPSEEK_API_KEY"]
        model = os.environ.get("PROXY_LLM_MODEL", "deepseek-chat")
    assert base_url and api_key, "no LLM credentials"

    samples = [json.loads(l) for l in open(args.data, encoding="utf-8") if l.strip()][:args.max_samples]

    os.makedirs(args.outdir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    outdir = os.path.join(args.outdir, stamp)
    os.makedirs(outdir, exist_ok=True)
    db_url = f"sqlite:///{(os.path.join(outdir, 'proxy.db')).replace(os.sep, '/')}"
    if os.path.isdir(r"D:\all-mpnet-base-v2"):
        os.environ.setdefault("MINTA_EVAL_EMBED_MODEL", r"D:\all-mpnet-base-v2")

    app = create_eval_app(db_url=db_url)
    with TestClient(app) as client:
        items = []
        for si, s in enumerate(samples):
            msgs = [m for m in s["messages"] if m.get("role") != "system"]
            if not msgs:
                continue
            query = msgs[-1]["content"]
            mem_parts = []
            for m in msgs[:-1]:
                mem_parts.extend({"role": "user" if m["role"] == "user" else "assistant",
                                  "content": c}
                                 for c in split_long_content(str(m.get("content", ""))))
            for ci, chunk in enumerate(chunk_requests(mem_parts)):
                r = client.post("/add", json={
                    "request_id": f"clb:{si}:{ci}", "user_id": f"clb:{si}",
                    "session_id": f"clb:{si}", "messages": chunk})
                assert r.status_code == 200, (si, ci, r.text)
            sr = client.post("/search", json={
                "query": query, "user_id": f"clb:{si}", "top_k": args.top_k})
            hits = sr.json()["data"]
            items.append({
                "id": str(si), "question": query[:2000],
                "rubrics": s.get("rubrics", []),
                "retrieved": [h["content"] for h in hits],
            })
    print(f"samples={len(items)}")

    client = httpx.Client()
    results = []
    for i, item in enumerate(items):
        if not item["rubrics"]:
            results.append({**item, "rubric_pass_rate": float("nan"), "n_rubrics": 0})
            continue
        mem_block = "\n".join(item["retrieved"][:80])
        ans_prompt = ("Answer the user's question using ONLY the retrieved "
                      "context passages. Be specific; reference exact names, "
                      "numbers and identifiers when they appear.\n\n"
                      f"Retrieved context:\n{mem_block}\n\nQuestion: {item['question']}\n\nAnswer:")
        answer = llm_complete(client, base_url, api_key, model, ans_prompt, max_tokens=512)
        judge = llm_complete(client, base_url, api_key, model,
                             rubric_judge_prompt(item["question"], answer, item["rubrics"]),
                             max_tokens=300)
        flags = parse_rubric_flags(judge, len(item["rubrics"]))
        rate = sum(flags) / len(flags)
        results.append({**item, "answer": answer, "rubric_flags": flags,
                        "rubric_pass_rate": rate, "n_rubrics": len(flags)})
        if (i + 1) % 10 == 0:
            cur = [x for x in results if x["n_rubrics"]]
            print(f"  {i+1}/{len(items)} — mean rubric pass "
                  f"{sum(x['rubric_pass_rate'] for x in cur)/len(cur):.3f}", flush=True)
    client.close()

    scored = [x for x in results if x["n_rubrics"]]
    mean = sum(x["rubric_pass_rate"] for x in scored) / len(scored) if scored else float("nan")
    all_pass = sum(1 for x in scored if x["rubric_pass_rate"] == 1.0) / len(scored) if scored else float("nan")
    print(f"\n=== CLBench proxy: mean rubric pass={mean:.3f} | all-pass rate={all_pass:.3f} "
          f"({len(scored)} samples, {sum(x['n_rubrics'] for x in scored)} rubrics) ===")
    with open(os.path.join(outdir, "items.jsonl"), "w", encoding="utf-8") as f:
        for x in results:
            f.write(json.dumps({k: x[k] for k in
                                ("id", "question", "rubric_pass_rate", "n_rubrics")},
                               ensure_ascii=False) + "\n")
    with open(os.path.join(outdir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump({"mean_rubric_pass": mean, "all_pass_rate": all_pass,
                   "n": len(scored), "n_rubrics": sum(x["n_rubrics"] for x in scored)},
                  f, ensure_ascii=False, indent=2)
    print("saved ->", outdir)


if __name__ == "__main__":
    main()

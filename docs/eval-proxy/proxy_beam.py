"""BEAM rehearsal: long-planning-chat memory + six probing categories.

Pit-hunting goals (BEAM probes map onto AML capability axes):
  * knowledge_update / contradiction_resolution — the memory-governance axis
    at the evidence level (newer facts must win, older ones stay retrievable);
  * event_ordering — relative-time/order questions over a multi-batch chat;
  * abstention — the system must NOT fabricate when evidence is absent;
  * information_extraction / instruction_following — plain recall.

Replay: memory = every chat message (user main_questions + assistant replies)
chunked by platform rules; timestamps synthesized from each batch's
time_anchor + ordinal minutes; a probing question is searched against that
history and judged against its ideal_response (abstention-aware: when the
ideal says "no information", a fabricating answer is wrong even if fluent).

Data: BEAM-main zip contains chats/100K/{id}/chat.json + probing_questions/
probing_questions.json. Extract the zip once; this runner reads the folder.

Usage:
    D:/pycharm/anaconda/python.exe docs/eval-proxy/proxy_beam.py --chats 3
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
from proxy_eval import llm_complete, parse_judge_label  # noqa: E402

BEAM_ROOT = r"D:\BEAM-main\chats\100K"
MAX_MSG_WORDS = 2000
MAX_REQ_MSGS = 20
_date_formats = ["%B-%d-%Y", "%b-%d-%Y", "%B %d, %Y", "%Y-%m-%d"]


def parse_anchor(s: str) -> int | None:
    s = (s or "").strip()
    for fmt in _date_formats:
        try:
            return int(datetime.strptime(s, fmt).timestamp() * 1000)
        except ValueError:
            continue
    return None


def split_long(text: str, max_words: int = MAX_MSG_WORDS) -> list[str]:
    if len(text.split()) <= max_words:
        return [text]
    sentences = re.split(r"(?<=[.!?])\s+|\n+", text)
    pieces, cur = [], []
    for s in sentences:
        s = s.strip()
        if not s:
            continue
        if cur and len(" ".join(cur).split()) + len(s.split()) > max_words:
            pieces.append(" ".join(cur)); cur = []
        cur.append(s)
    if cur:
        pieces.append(" ".join(cur))
    return pieces


def flatten_chat(chat: list[dict]) -> list[dict]:
    """Yield ordered messages with synthesized timestamps from batch anchors."""
    out = []
    for batch in chat:
        base = parse_anchor(batch.get("time_anchor")) or 1_700_000_000_000
        idx = 0
        for turn in batch.get("turns", []):
            for msg in turn if isinstance(turn, list) else [turn]:
                role = msg.get("role")
                if role not in ("user", "assistant"):
                    continue
                content = str(msg.get("content", ""))
                for piece in split_long(content):
                    out.append({"role": role, "content": piece,
                                "timestamp": base + idx * 60_000})
                    idx += 1
    return out


def judge_prompt(question: str, ideal: str, generated: str) -> str:
    return (
        "Judge whether the answer is CORRECT or WRONG for a memory question.\n"
        "Rules:\n"
        "- If the ideal response states there is no such information, the "
        "answer must say so / decline; any fabricated detail is WRONG.\n"
        "- Otherwise the answer must contain the ideal's key content "
        "(paraphrase ok); extra unverifiable details are tolerated only if "
        "they do not contradict.\n"
        f"Question: {question}\nIdeal: {ideal}\nGenerated: {generated}\n\n"
        "Reply in JSON: {\"label\": \"CORRECT\" or \"WRONG\"}"
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=BEAM_ROOT)
    ap.add_argument("--chats", type=int, default=3)
    ap.add_argument("--top-k", type=int, default=100)
    ap.add_argument("--outdir", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "runs", "beam"))
    args = ap.parse_args()

    base_url = os.environ.get("PROXY_LLM_BASE", "")
    api_key = os.environ.get("PROXY_LLM_KEY", "")
    model = os.environ.get("PROXY_LLM_MODEL", "gpt-4o-mini")
    if not (base_url and api_key) and os.environ.get("DEEPSEEK_API_KEY"):
        base_url = base_url or "https://api.deepseek.com/v1"
        api_key = os.environ["DEEPSEEK_API_KEY"]
        model = os.environ.get("PROXY_LLM_MODEL", "deepseek-chat")
    assert base_url and api_key, "no LLM credentials"

    chat_ids = sorted(
        d for d in os.listdir(args.root)
        if d.isdigit() and os.path.isdir(os.path.join(args.root, d))
    )[: args.chats]
    print("chats:", chat_ids)

    os.makedirs(args.outdir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    outdir = os.path.join(args.outdir, stamp)
    os.makedirs(outdir, exist_ok=True)
    db_url = f"sqlite:///{(os.path.join(outdir, 'proxy.db')).replace(os.sep, '/')}"
    if os.path.isdir(r"D:\all-mpnet-base-v2"):
        os.environ.setdefault("MINTA_EVAL_EMBED_MODEL", r"D:\all-mpnet-base-v2")

    app = create_eval_app(db_url=db_url)
    items = []
    with TestClient(app) as client:
        for cid in chat_ids:
            cdir = os.path.join(args.root, cid)
            chat = json.load(open(os.path.join(cdir, "chat.json"), encoding="utf-8"))
            msgs = flatten_chat(chat)
            # chunk into Add requests (<=20 msgs each)
            reqs = [msgs[i:i + MAX_REQ_MSGS] for i in range(0, len(msgs), MAX_REQ_MSGS)]
            for ri, req in enumerate(reqs):
                r = client.post("/add", json={
                    "request_id": f"beam:{cid}:{ri}", "user_id": f"beam:{cid}",
                    "session_id": f"beam:{cid}", "messages": req})
                assert r.status_code == 200, (cid, ri, r.text)
            pq = json.load(open(os.path.join(cdir, "probing_questions",
                                             "probing_questions.json"), encoding="utf-8"))
            for cat, qlist in pq.items():
                for q in qlist:
                    sr = client.post("/search", json={
                        "query": q["question"], "user_id": f"beam:{cid}",
                        "top_k": args.top_k})
                    hits = sr.json()["data"]
                    items.append({
                        "id": f"{cid}:{cat}:{len(items)}", "chat": cid,
                        "category": cat, "question": q["question"],
                        "ideal": q.get("ideal_response", ""),
                        "difficulty": q.get("difficulty", ""),
                        "retrieved": [h["content"] for h in hits],
                    })
    print(f"chats={len(chat_ids)} probes={len(items)}")

    client = httpx.Client()
    results = []
    for i, item in enumerate(items):
        mem = "\n".join(item["retrieved"][:80])
        ans_prompt = (
            "Answer from the retrieved conversation memory only. If the "
            "memory does not contain the answer, say so plainly — do not "
            "invent details.\n\nRetrieved memory:\n" + mem +
            f"\n\nQuestion: {item['question']}\n\nAnswer:")
        gen = llm_complete(client, base_url, api_key, model, ans_prompt, max_tokens=200)
        judge = llm_complete(client, base_url, api_key, model,
                             judge_prompt(item["question"], item["ideal"], gen),
                             max_tokens=120)
        try:
            label = parse_judge_label(judge)
        except ValueError:
            label = "WRONG"
        results.append({**item, "label": label, "is_correct": label == "CORRECT"})
        if (i + 1) % 20 == 0:
            acc = sum(x["is_correct"] for x in results) / len(results)
            print(f"  {i+1}/{len(items)} — acc {acc:.3f}", flush=True)
    client.close()

    from collections import defaultdict
    by_cat = defaultdict(list)
    for x in results:
        by_cat[x["category"]].append(x["is_correct"])
    overall = sum(x["is_correct"] for x in results) / len(results)
    print(f"\n=== BEAM proxy: acc={overall:.3f} ({len(results)} probes) ===")
    for c, v in sorted(by_cat.items()):
        print(f"  {c:<26} {sum(v)/len(v):.3f} (n={len(v)})")
    with open(os.path.join(outdir, "items.jsonl"), "w", encoding="utf-8") as f:
        for x in results:
            f.write(json.dumps({k: x.get(k) for k in
                                ("id", "category", "question", "label", "is_correct",
                                 "difficulty")}, ensure_ascii=False) + "\n")
    with open(os.path.join(outdir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump({"overall": overall, "n": len(results),
                   "by_category": {c: sum(v)/len(v) for c, v in by_cat.items()}},
                  f, ensure_ascii=False, indent=2)
    print("saved ->", outdir)


if __name__ == "__main__":
    main()

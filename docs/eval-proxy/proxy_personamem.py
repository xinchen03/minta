"""PersonaMem-v2 rehearsal: long-history implicit-persona multiple choice.

Pit-hunting goals:
  * 128k/32k-scale per-persona history — is fill-top_k=100 enough evidence
    when one user has thousands of messages?
  * four-option MCQ — deterministic exact-option scoring (official style),
    one LLM call per question;
  * preference-change rows (prev_pref / updated present) — a real probe of
    the memory-governance axis at the evidence level.

Persona dump messages (role=system) are excluded, mirroring the official
pipeline's "context_messages: already-sliced conversation history" — reading
the persona file would be a cheat no platform run would allow.

Data (already downloaded): D:/PersonaMem-v2-sel/chat32k/*.json +
val_rows_selected.json (24 personas).
Usage:
    D:/pycharm/anaconda/python.exe docs/eval-proxy/proxy_personamem.py
"""
from __future__ import annotations

import argparse
import ast
import io
import json
import os
import random
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

DATA = r"D:\PersonaMem-v2-sel"
CHAT_DIR = os.path.join(DATA, "chat32k")
ROWS_FILE = os.path.join(DATA, "val_rows_selected.json")
LETTERS = "ABCD"


def _paths_from_args(args):
    """Resolve chat dir / rows file (cloud runs use explicit paths)."""
    chat_dir = args.chat_dir or CHAT_DIR
    rows_file = args.rows_file or ROWS_FILE
    return chat_dir, rows_file


def _as_obj(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        return value
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in ("nan", "none", "null"):
        return None
    try:
        return json.loads(s)
    except Exception:
        pass
    try:
        return ast.literal_eval(s)
    except Exception:
        return s


def parse_date(s) -> int | None:
    """PersonaMem chat may embed a start date in metadata; best effort ms."""
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S", "%B %d, %Y"):
        try:
            return int(datetime.strptime(str(s).strip(), fmt).timestamp() * 1000)
        except ValueError:
            continue
    return None


def chunker(msgs: list[dict], max_msgs: int = 20, max_words: int = 2000):
    chunks, cur = [], []
    for m in msgs:
        if len(cur) >= max_msgs:
            chunks.append(cur); cur = []
        cur.append(m)
    if cur:
        chunks.append(cur)
    return chunks


def mc_prompt(question: str, options: list[str], memories: list[str]) -> str:
    body = "\n".join(f"{LETTERS[i]}. {o}" for i, o in enumerate(options))
    mem = "\n".join(memories[:60]) if memories else "(no memories retrieved)"
    return (
        "You answer a multiple-choice question about a person, using only "
        "retrieved conversation memories as evidence.\n\n"
        f"Retrieved memories:\n{mem}\n\n"
        f"Question: {question}\n\nOptions:\n{body}\n\n"
        "Reply with the single option letter only (A, B, C or D)."
    )


def parse_letter(text: str) -> str | None:
    m = re.search(r"\b([A-D])\b", text or "", re.I)
    return m.group(1).upper() if m else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top-k", type=int, default=100)
    ap.add_argument("--outdir", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "runs", "personamem"))
    ap.add_argument("--personas", type=int, default=24)
    ap.add_argument("--chat-dir", default="")
    ap.add_argument("--rows-file", default="")
    args = ap.parse_args()
    CHAT_DIR, ROWS_FILE = _paths_from_args(args)  # noqa: F841  (used below)

    base_url = os.environ.get("PROXY_LLM_BASE", "")
    api_key = os.environ.get("PROXY_LLM_KEY", "")
    model = os.environ.get("PROXY_LLM_MODEL", "gpt-4o-mini")
    if not (base_url and api_key) and os.environ.get("DEEPSEEK_API_KEY"):
        base_url = base_url or "https://api.deepseek.com/v1"
        api_key = os.environ["DEEPSEEK_API_KEY"]
        model = os.environ.get("PROXY_LLM_MODEL", "deepseek-chat")
    assert base_url and api_key, "no LLM credentials"

    rows = json.load(open(ROWS_FILE, encoding="utf-8"))
    personas = {}
    for r in rows:
        personas.setdefault(str(r["persona_id"]), []).append(r)
    chosen = list(personas.items())[: args.personas]

    os.makedirs(args.outdir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    outdir = os.path.join(args.outdir, stamp)
    os.makedirs(outdir, exist_ok=True)
    db_url = f"sqlite:///{(os.path.join(outdir, 'proxy.db')).replace(os.sep, '/')}"
    if os.path.isdir(r"D:\all-mpnet-base-v2"):
        os.environ.setdefault("MINTA_EVAL_EMBED_MODEL", r"D:\all-mpnet-base-v2")

    app = create_eval_app(db_url=db_url)
    with TestClient(app) as client:
        q_items = []
        for pid, prow_rows in chosen:
            chat_path = os.path.join(CHAT_DIR, f"chat_history_250913_163134_persona{pid}.json")
            if not os.path.exists(chat_path):
                # filename stem varies; fall back to any file containing the id
                cands = [f for f in os.listdir(CHAT_DIR) if f"persona{pid}." in f]
                if not cands:
                    print(f"skip persona {pid}: no chat file"); continue
                chat_path = os.path.join(CHAT_DIR, cands[0])
            chat = json.load(open(chat_path, encoding="utf-8"))
            msgs = [m for m in chat["chat_history"] if m.get("role") != "system"]
            base_ts = parse_date(chat.get("metadata", {}).get("start_date")
                                 or chat.get("metadata", {}).get("date"))
            for ci, chunk in enumerate(chunker(msgs)):
                payload_msgs = []
                for i, m in enumerate(chunk):
                    pm = {"role": "user" if m.get("role") == "user" else "assistant",
                          "content": str(m.get("content", ""))[:4000]}
                    if base_ts:
                        pm["timestamp"] = base_ts + (ci * len(chunk) + i) * 60_000
                    payload_msgs.append(pm)
                r = client.post("/add", json={
                    "request_id": f"pm:{pid}:{ci}", "user_id": f"pm:{pid}",
                    "session_id": f"pm:{pid}", "messages": payload_msgs})
                assert r.status_code == 200, (pid, ci, r.text)
            for r in prow_rows:
                q = _as_obj(r.get("user_query")) or {}
                question = q.get("content") if isinstance(q, dict) else str(q)
                correct = str(r.get("correct_answer") or "")
                wrongs = _as_obj(r.get("incorrect_answers")) or []
                wrongs = [str(w) for w in wrongs][:3]
                options = [correct] + wrongs
                rng = random.Random(hash(str(r.get("user_query")) + pid) & 0xFFFF)
                rng.shuffle(options)
                gold_letter = LETTERS[options.index(correct)]
                sr = client.post("/search", json={
                    "query": question, "user_id": f"pm:{pid}", "top_k": args.top_k})
                hits = sr.json()["data"]
                upd = str(r.get("updated") or "").strip().lower()
                is_change = bool(r.get("prev_pref")) or upd not in ("", "false", "nan", "none", "null")
                q_items.append({
                    "id": f"{pid}:{rng.getrandbits(32):x}", "persona": pid,
                    "question": question, "gold_letter": gold_letter,
                    "options": options, "is_preference_change": is_change,
                    "pref_type": r.get("pref_type", ""),
                    "retrieved": [h["content"] for h in hits],
                    "correct_answer": correct,
                })

    print(f"personas={len(chosen)} questions={len(q_items)}")
    client = httpx.Client()
    results = []
    for i, item in enumerate(q_items):
        gen = llm_complete(client, base_url, api_key, model,
                           mc_prompt(item["question"], item["options"], item["retrieved"]),
                           max_tokens=32)
        pred = parse_letter(gen)
        results.append({**item, "pred": pred, "is_correct": pred == item["gold_letter"]})
        if (i + 1) % 20 == 0:
            acc = sum(x["is_correct"] for x in results) / len(results)
            print(f"  {i+1}/{len(q_items)} — acc {acc:.3f}", flush=True)
    client.close()

    def acc(xs):
        return sum(x["is_correct"] for x in xs) / len(xs) if xs else float("nan")

    print(f"\n=== PersonaMem proxy: acc={acc(results):.3f} ({len(results)} q) ===")
    change = [x for x in results if x["is_preference_change"]]
    plain = [x for x in results if not x["is_preference_change"]]
    print(f"  preference-change rows: {acc(change):.3f} (n={len(change)})")
    print(f"  other rows:             {acc(plain):.3f} (n={len(plain)})")
    with open(os.path.join(outdir, "items.jsonl"), "w", encoding="utf-8") as f:
        for x in results:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")
    with open(os.path.join(outdir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump({"overall": acc(results), "n": len(results),
                   "pref_change_acc": acc(change), "pref_change_n": len(change),
                   "plain_acc": acc(plain), "plain_n": len(plain)},
                  f, ensure_ascii=False, indent=2)
    print("saved ->", outdir)


if __name__ == "__main__":
    main()

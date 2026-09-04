"""Proxy evaluation harness: LoCoMo → Minta eval app → AML-format scoring.

Purpose (AMC cycle-2, private): before the official smoke/full run we cannot
see the held-out suite, so this harness replays the PUBLIC LoCoMo data through
our own eval adapter and scores it with the OFFICIAL answer/judge templates
(docs/eval-proxy/templates.py, verbatim from AML-memory's public repo). The
result is a tuning signal only — not a leaderboard prediction.

Discipline (per the v3 design review):
  * coverage diagnostics are printed for insight only; tuning optimises the
    end-to-end accuracy, never coverage alone
  * benchmark content is eval-only: written to the private run dir, never
    logged by the adapter, deleted with the run dir when done

Usage:
    # retrieval-only dry pass (no LLM key needed):
    python docs/eval-proxy/proxy_eval.py --max-convs 2 --max-questions 20

    # full scoring pass (export your own OpenAI-compatible creds):
    export PROXY_LLM_BASE=... PROXY_LLM_KEY=... PROXY_LLM_MODEL=gpt-4o-mini
    python docs/eval-proxy/proxy_eval.py --max-convs 10 --top-k 100

Requires the repo dev env (anaconda python) and the local mpnet weights
(default D:/all-mpnet-base-v2, overridable via MINTA_EVAL_EMBED_MODEL).
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
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
from templates import ACCURACY_PROMPT, OPEN_ENDED_ANSWER_TEMPLATE  # noqa: E402

CATEGORIES = {1: "single-hop", 2: "multi-hop", 3: "temporal",
              4: "open-domain", 5: "adversarial"}
DEFAULT_DATA = r"D:\locomo-main\locomo-main\data\locomo10.json"
CHUNK_MAX_MESSAGES = 20
CHUNK_MAX_WORDS = 2000

_session_date_formats = ["%I:%M %p on %d %B %Y", "%I:%M %p on %d %B, %Y"]


def parse_session_date(s: str):
    s = s.replace("Sept ", "Sep ").replace(".", "")
    for fmt in _session_date_formats:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def chunk_messages(turns: list[dict]) -> list[list[dict]]:
    """Emulate the platform chunking rule: ≤20 messages / ≤2000 words."""
    chunks: list[list[dict]] = [[]]
    for t in turns:
        if (len(chunks[-1]) >= CHUNK_MAX_MESSAGES
                or _words(chunks[-1]) + _words([t]) > CHUNK_MAX_WORDS):
            chunks.append([])
        chunks[-1].append(t)
    return chunks


def _words(msgs: list[dict]) -> int:
    return sum(len(str(m.get("text", "")).split()) for m in msgs)


def epoch_ms(dt: datetime) -> int:
    return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)


def load_convs(path: str):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_add_plan(conv: dict, sample_id: str):
    """Flatten sessions into role-mapped messages + dia registry.

    Returns (adds, dia_map) where adds is a list of
    (user_id, request_id, session_id, messages[]) and dia_map maps
    dia_id -> (user_id, request_id, msg_index) for coverage diagnostics.
    """
    co = conv["conversation"]
    speaker_a = co.get("speaker_a")
    adds = []
    dia_map = {}
    chunk_no = 0
    for key, val in co.items():
        if not (key.startswith("session_") and not key.endswith("_date_time")
                and isinstance(val, list)):
            continue
        dt_key = key + "_date_time"
        base_dt = parse_session_date(co.get(dt_key, "")) or datetime(2023, 1, 1)
        turns = []
        for i, t in enumerate(val):
            role = "user" if t.get("speaker") == speaker_a else "assistant"
            turns.append({
                "role": role,
                "content": t.get("text", ""),
                "timestamp": epoch_ms(base_dt) + i * 60_000,
                "dia_id": t.get("dia_id", f"{key}:{i}"),
            })
        for chunk in chunk_messages(turns):
            req_id = f"proxy:{sample_id}:{chunk_no}"
            session_id = f"proxy:{sample_id}:{key}"
            msgs = [{"role": m["role"], "content": m["content"],
                     "timestamp": m["timestamp"]} for m in chunk]
            adds.append((f"proxy:{sample_id}", req_id, session_id, msgs))
            for j, m in enumerate(chunk):
                dia_map[m["dia_id"]] = (f"proxy:{sample_id}", req_id, j)
            chunk_no += 1
    return adds, dia_map


def render_answer_prompt(question: str, memories: list[str]) -> str:
    values = {
        "speaker_1_name": "speaker 1",
        "speaker_1_memories": "\n".join(str(m) for m in memories),
        "speaker_2_name": "speaker 2",
        "speaker_2_memories": "",
        "question": question,
    }
    return re.sub(
        r"\{\{(speaker_1_name|speaker_1_memories|speaker_2_name|speaker_2_memories|question)\}\}",
        lambda m: str(values[m.group(1)]), OPEN_ENDED_ANSWER_TEMPLATE)


def render_judge_prompt(question: str, gold, generated: str) -> str:
    # gold answers may be numeric (JSON parses "3" as int) — coerce to str
    values = {"question": str(question), "gold_answer": str(gold),
              "generated_answer": str(generated)}
    return re.sub(r"\{(question|gold_answer|generated_answer)\}",
                  lambda m: values[m.group(1)], ACCURACY_PROMPT)


def llm_complete(client: httpx.Client, base: str, key: str, model: str,
                 prompt: str, max_tokens: int = 256, attempts: int = 3) -> str:
    """Chat-completions call with bounded retry on 429/5xx (parallel runs
    share the provider's rate limit; a retry makes concurrency survivable)."""
    import time

    last: Exception | None = None
    for i in range(attempts):
        try:
            r = client.post(base.rstrip("/") + "/chat/completions",
                            headers={"Authorization": f"Bearer {key}"},
                            json={"model": model,
                                  "messages": [{"role": "user", "content": prompt}],
                                  "temperature": 0},
                            timeout=120)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"].strip()
        except Exception as exc:  # noqa: BLE001 — retry transport & 429/5xx
            last = exc
            status = getattr(exc, "response", None)
            code = getattr(status, "status_code", None)
            if code not in (429, 500, 502, 503, 504) and not isinstance(exc, httpx.TransportError):
                raise
            time.sleep(2 ** (i + 1))
    raise last  # type: ignore[misc]


def parse_judge_label(response: str) -> str:
    """Tolerant label extraction (models may emit single-quoted JSON or prose)."""
    m = re.search(r"['\"]?label['\"]?\s*[:=]\s*['\"](CORRECT|WRONG)['\"]", response, re.I)
    if m:
        return m.group(1).upper()
    m = re.search(r"\{.*?\}", response, re.DOTALL)
    if m:
        try:
            payload = json.loads(m.group(0).replace("'", '"'))
            label = str(payload.get("label", "")).upper()
            if label in {"CORRECT", "WRONG"}:
                return label
        except json.JSONDecodeError:
            pass
    raise ValueError(f"judge label not found in: {response[:200]!r}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--convs", default=os.environ.get("PROXY_DATA", DEFAULT_DATA))
    ap.add_argument("--max-convs", type=int, default=2)
    ap.add_argument("--max-questions", type=int, default=20)
    ap.add_argument("--top-k", type=int, default=100)
    ap.add_argument("--outdir", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "runs"))
    args = ap.parse_args()

    # Credential resolution: PROXY_LLM_* first, DeepSeek as a local fallback
    # (OpenAI-compatible). Swap back to GPT later by exporting PROXY_LLM_* —
    # the interface is the same; only the judge/answer model changes.
    base_url = os.environ.get("PROXY_LLM_BASE", "")
    api_key = os.environ.get("PROXY_LLM_KEY", "")
    model = os.environ.get("PROXY_LLM_MODEL", "gpt-4o-mini")
    if not (base_url and api_key) and os.environ.get("DEEPSEEK_API_KEY"):
        base_url = base_url or "https://api.deepseek.com/v1"
        api_key = os.environ["DEEPSEEK_API_KEY"]
        model = os.environ.get("PROXY_LLM_MODEL", "deepseek-chat")
        print("LLM: DeepSeek fallback (deepseek-chat) — proxy signal only; "
              "export PROXY_LLM_* to switch to gpt-4o-mini later")
    do_score = bool(base_url and api_key)

    os.makedirs(args.outdir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    outdir = os.path.join(args.outdir, stamp)
    os.makedirs(outdir, exist_ok=True)
    db_url = f"sqlite:///{(os.path.join(outdir, 'proxy.db')).replace(os.sep, '/')}"

    if os.path.isdir(r"D:\all-mpnet-base-v2"):
        os.environ.setdefault("MINTA_EVAL_EMBED_MODEL", r"D:\all-mpnet-base-v2")

    # ── load + add ──────────────────────────────────────────────────────────
    convs = load_convs(args.convs)[:args.max_convs]
    app = create_eval_app(db_url=db_url)  # real mpnet embedder, env defaults
    print(f"run dir: {outdir}\nconvs: {len(convs)} | scoring: {do_score} "
          f"(model {model})\n")
    t0 = time.time()

    with TestClient(app) as client:
        q_items = []
        for conv in convs:
            sample = conv["sample_id"]
            adds, dia_map = build_add_plan(conv, sample)
            for user_id, req_id, sess_id, msgs in adds:
                r = client.post("/add", json={
                    "request_id": req_id, "user_id": user_id,
                    "session_id": sess_id, "messages": msgs})
                assert r.status_code == 200, (req_id, r.text)
            n_q = min(args.max_questions, len(conv["qa"]))
            print(f"[{sample}] added {len(adds)} chunks, scanning {n_q} questions...")
            for qa in conv["qa"][:n_q]:
                question = qa["question"]
                r = client.post("/search", json={
                    "query": question, "user_id": user_id, "top_k": args.top_k})
                assert r.status_code == 200
                hits = r.json()["data"]
                # coverage diagnostics (insight only — never a tuning target)
                ev = [dia_map[e] for e in qa.get("evidence", []) if e in dia_map]
                cov = 0.0
                if ev:
                    ids = {h["id"] for h in hits}
                    cov = sum(1 for uid, req, idx in ev
                              if mem_id(req, idx) in ids) / len(ev)
                q_items.append({
                    "id": f"{sample}:{len(q_items)}",
                    "sample_id": sample,
                    "question": question,
                    "gold": qa.get("answer", ""),
                    "category": CATEGORIES.get(qa.get("category"), "other"),
                    "evidence": qa.get("evidence", []),
                    "retrieved": [h["content"] for h in hits],
                    "coverage@k": round(cov, 3),
                })

    print(f"ingest+retrieval done in {time.time() - t0:.0f}s — "
          f"{len(q_items)} items, mean coverage@{args.top_k} "
          f"= {sum(i['coverage@k'] for i in q_items)/len(q_items):.3f}")

    if not do_score:
        print("no PROXY_LLM_KEY set — answer/eval stage skipped "
              "(retrieval dry pass only)")
        _save(q_items, outdir, None)
        return

    # ── answer + judge (official templates, temp 0) ─────────────────────────
    client = httpx.Client()
    results = []
    for i, item in enumerate(q_items):
        ans_prompt = render_answer_prompt(item["question"], item["retrieved"])
        generated = llm_complete(client, base_url, api_key, model, ans_prompt)
        judge_prompt = render_judge_prompt(item["question"], item["gold"], generated)
        judge_resp = llm_complete(client, base_url, api_key, model, judge_prompt)
        label = parse_judge_label(judge_resp)
        results.append({**item, "generated": generated,
                        "label": label, "is_correct": label == "CORRECT"})
        if (i + 1) % 20 == 0:
            cur = sum(r["is_correct"] for r in results) / len(results)
            print(f"  {i + 1}/{len(q_items)} judged — running acc {cur:.3f}")
    client.close()

    overall = sum(r["is_correct"] for r in results) / len(results)
    by_cat = defaultdict(list)
    for r in results:
        by_cat[r["category"]].append(r["is_correct"])
    print(f"\n=== proxy accuracy: {overall:.3f} "
          f"({sum(r['is_correct'] for r in results)}/{len(results)}) ===")
    for cat, vals in sorted(by_cat.items()):
        print(f"  {cat:<12} {sum(vals)/len(vals):.3f}  (n={len(vals)})")
    _save(results, outdir, {"overall": overall, "by_category":
                            {c: sum(v)/len(v) for c, v in by_cat.items()},
                            "mean_coverage": sum(i["coverage@k"] for i in results)/len(results)})


def _save(items: list[dict], outdir: str, summary: dict | None) -> None:
    with open(os.path.join(outdir, "items.jsonl"), "w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    if summary is not None:
        with open(os.path.join(outdir, "summary.json"), "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"saved -> {outdir}")


if __name__ == "__main__":
    main()

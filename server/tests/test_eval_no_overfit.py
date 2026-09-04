"""Anti-overfit tripwires for the AMC eval adapter (AML red lines).

These tests fail if the adapter code starts carrying anything that could be
read as benchmark gaming, however well-intentioned:

  * dataset/sample/question literals ("conv-26", "qa_id", question strings)
  * hardcoded answers or gold fragments
  * eval-only special cases keyed by request/user/sample patterns

The adapter must stay a GENERIC memory engine: everything it does has to be
explainable for arbitrary conversations it has never seen. Tuning happens on
public data but only through mechanism knobs (env flags) — never through
code that names a sample, a question or a dataset artifact.
"""
from __future__ import annotations

import os
import re

_EVAL_SRC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "eval")
_FORBIDDEN_PATTERNS = [
    # quoted literals that would name a specific sample/question/dataset
    r'"(?:conv|sample|qa)[-_][A-Za-z0-9_-]*"',
    r'"(?:locomo10|longmemeval|scriptmem|personamem|clbench|beam)[-_]?[^"]*"',
    r'"(?:q\d{4}|D\d+:\d+)"',          # qa ids like q0000, evidence ids D1:3
    r'"(?:Which answer best matches|When did|What did|Where does)[^"]{10,}"',  # question-shaped strings
    r'"gold[_a-z]*"\s*[:=]\s*"',       # gold answers written into code
]
_FORBIDDEN_RAW = ["sk-", "OPENAI_API_KEY=", "DEEPSEEK_API_KEY="]


def _eval_files():
    for root, _dirs, files in os.walk(_EVAL_SRC_DIR):
        for f in files:
            if f.endswith(".py"):
                yield os.path.join(root, f)


def test_no_dataset_or_question_literals():
    hits = []
    for path in _eval_files():
        src = open(path, encoding="utf-8").read()
        for pat in _FORBIDDEN_PATTERNS:
            for m in re.finditer(pat, src, re.I):
                hits.append(f"{os.path.basename(path)}: {m.group(0)[:80]}")
    assert not hits, f"dataset/question literals found in eval code:\n" + "\n".join(hits)


def test_no_credentials_in_eval_code():
    hits = []
    for path in _eval_files():
        src = open(path, encoding="utf-8").read()
        for tok in _FORBIDDEN_RAW:
            if tok in src:
                hits.append(os.path.basename(path))
    assert not hits, f"credential-like tokens in eval code: {hits}"

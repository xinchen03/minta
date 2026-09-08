"""Fail CI when the public tree contains private paths, secrets, or runtime data."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {
    ".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".json", ".md",
    ".yml", ".yaml", ".toml", ".ini", ".cfg", ".example", ".txt",
}
PROHIBITED_DIRS = {
    "chroma_data", "knowledge-atoms", "fact_spine", "logs", "runs",
}
PROHIBITED_SUFFIXES = {".db", ".sqlite", ".sqlite3"}
PATTERNS = {
    "OpenAI-style secret": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "GitHub token": re.compile(r"\b(?:ghp|github_pat)_[A-Za-z0-9_]{20,}\b"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "private workstation path": re.compile(
        r"(?:[A-Za-z]:[/\\](?:Users|Minta|Documents|Desktop)[/\\]|"
        r"/(?:home|Users)/[A-Za-z0-9._-]+/)"
    ),
    "private key material": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}


def repository_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT, check=True, capture_output=True,
    )
    return [ROOT / item.decode("utf-8") for item in result.stdout.split(b"\0") if item]


def scan() -> list[str]:
    findings = []
    for path in repository_files():
        relative = path.relative_to(ROOT)
        parts = {part.lower() for part in relative.parts}
        if parts & PROHIBITED_DIRS or path.suffix.lower() in PROHIBITED_SUFFIXES:
            findings.append(f"prohibited path: {relative.as_posix()}")
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for label, pattern in PATTERNS.items():
            if pattern.search(text):
                findings.append(f"{label}: {relative.as_posix()}")
    return findings


if __name__ == "__main__":
    problems = scan()
    if problems:
        print("Public-boundary check failed:")
        for problem in problems:
            print(f"- {problem}")
        raise SystemExit(1)
    print("Public-boundary check passed")

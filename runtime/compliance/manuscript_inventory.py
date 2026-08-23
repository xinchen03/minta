"""ManuscriptInventory — scans a manuscript directory and builds a structured inventory."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class ManuscriptInventory:
    def __init__(self, source_path: str | Path):
        self._root = Path(source_path)

    def build_inventory(self) -> Dict[str, Any]:
        """Scan the source directory and return structured inventory."""
        files = []
        for f in sorted(self._root.rglob("*")):
            if f.is_file() and not f.name.startswith("."):
                rel = str(f.relative_to(self._root))
                files.append({
                    "path": rel,
                    "size_bytes": f.stat().st_size,
                    "sha256": self._hash_file(f),
                })

        # Identify key components
        tex_files = [f for f in files if f["path"].endswith(".tex")]
        bib_files = [f for f in files if f["path"].endswith(".bib")]
        pdf_files = [f for f in files if f["path"].endswith(".pdf")]
        fig_files = [f for f in files if any(f["path"].lower().endswith(ext) for ext in
                         (".png", ".jpg", ".jpeg", ".pdf", ".eps", ".tiff", ".svg"))]

        # Extract basic manuscript metadata from tex files
        abstract_word_count = self._count_abstract_words(tex_files)
        section_count = self._count_sections(tex_files)

        return {
            "source_path": str(self._root),
            "scanned_at": datetime.now(timezone.utc).isoformat(),
            "file_count": len(files),
            "total_size_bytes": sum(f["size_bytes"] for f in files),
            "files": files,
            "components": {
                "tex_files": len(tex_files),
                "bib_files": len(bib_files),
                "pdf_files": len(pdf_files),
                "figure_files": len(fig_files),
            },
            "manuscript_metadata": {
                "abstract_word_count": abstract_word_count,
                "section_count": section_count,
                "has_conclusions": self._section_exists(tex_files, 'conclusion'),
                "has_acknowledgements": self._section_exists(tex_files, 'acknowledg'),
                "has_appendix": self._section_exists(tex_files, 'appendix'),
                "has_supplementary": any("supplement" in f["path"].lower() for f in files),
            },
        }

    def freeze_baseline(self) -> Dict[str, Any]:
        """Create an immutable baseline manifest with hashes."""
        inventory = self.build_inventory()
        baseline = {
            **inventory,
            "frozen_at": datetime.now(timezone.utc).isoformat(),
            "immutable": True,
            "manifest_hash": self._hash_dict(inventory["files"]),
        }
        return baseline

    def verify_integrity(self, baseline: Dict[str, Any]) -> bool:
        """Verify that all files in baseline are unchanged."""
        for f in baseline.get("files", []):
            path = self._root / f["path"]
            if not path.exists():
                return False
            if self._hash_file(path) != f["sha256"]:
                return False
        return True

    @staticmethod
    def _hash_file(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as fp:
            for chunk in iter(lambda: fp.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def _hash_dict(obj: Any) -> str:
        h = hashlib.sha256()
        h.update(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode())
        return h.hexdigest()

    def _count_abstract_words(self, tex_files: List[dict]) -> Optional[int]:
        """Count words in abstract environment across tex files."""
        for f in tex_files:
            path = self._root / f["path"]
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
                import re
                # Match \\begin{abstract}...\\end{abstract}
                m = re.search(r'\\begin\{abstract\}(.+?)\\end\{abstract\}', content, re.DOTALL)
                if m:
                    text = re.sub(r'\\[a-zA-Z]+\{.*?\}', '', m.group(1))  # strip LaTeX commands
                    text = re.sub(r'[~%$&#_{}]', '', text)
                    return len(text.split())
            except Exception:
                pass
        return None

    def _count_sections(self, tex_files: List[dict]) -> int:
        """Count \\section{} commands across tex files."""
        count = 0
        for f in tex_files:
            path = self._root / f["path"]
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
                import re
                count += len(re.findall(r'\\section\{', content))
            except Exception:
                pass
        return count

    def _section_exists(self, tex_files: List[dict], keyword: str) -> bool:
        """Check if a section containing keyword exists in any tex file.
        Checks both \\section{...} command and file naming conventions."""
        for f in tex_files:
            # Check file name
            if keyword in f["path"].lower():
                return True
            # Check section commands in content
            path = self._root / f["path"]
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
                import re
                if re.search(rf'\\section\*?\{{.*?{keyword}.*?\}}', content, re.IGNORECASE):
                    return True
            except Exception:
                pass
        return False

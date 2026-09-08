"""Codex MCP configuration regression tests."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import minta_cli


def test_codex_config_replaces_obsolete_stdio_block(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text(
        'model = "gpt-test"\n\n'
        '[mcp_servers.minta]\n'
        'type = "stdio"\n'
        'command = "python"\n'
        'args = ["missing/minta_mcp.py"]\n\n'
        '[mcp_servers.other]\n'
        'command = "other"\n',
        encoding="utf-8",
    )

    minta_cli._write_codex_mcp(config)
    result = config.read_text(encoding="utf-8")

    assert 'model = "gpt-test"' in result
    assert '[mcp_servers.other]' in result
    assert 'command = "other"' in result
    assert 'missing/minta_mcp.py' not in result
    assert result.count('[mcp_servers.minta]') == 1
    assert minta_cli._codex_mcp_configured(config)


def test_codex_config_upsert_is_idempotent(tmp_path):
    config = tmp_path / "config.toml"
    minta_cli._write_codex_mcp(config)
    first = config.read_text(encoding="utf-8")
    minta_cli._write_codex_mcp(config)
    assert config.read_text(encoding="utf-8") == first


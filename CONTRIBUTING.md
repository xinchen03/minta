# Contributing to Minta

Thanks for your interest! Minta is a memory quality maintenance system for AI agents.

## Quick Setup

```bash
git clone https://github.com/chenxin99/minta.git
cd minta
pip install -r requirements.txt
python run.py
```

## Development

- **Python**: 3.10+
- **Database**: SQLite (default, zero config) or MySQL
- **Vector store**: ChromaDB (embedded, no server needed)

## Project Structure

```
server/
├── services/         Core algorithms (lifecycle, decay, conflict, retrieval)
├── routers/          FastAPI endpoints
├── models/           SQLAlchemy models
├── minta_mcp.py      MCP tools (stdio)
├── minta_mcp_http.py MCP tools (HTTP)
└── main.py           API server entry point

evaluation/           Benchmarks (LongMemEval, LoCoMo)
web/                  React frontend
docs/                 Documentation
```

## How to Contribute

**Never contributed to open source before?** This is a good place to start. We're friendly to newcomers.

### 1. Find something to work on
- Browse [Issues](https://github.com/chenxin99/minta/issues) tagged `good first issue`
- Or open a new issue to discuss your idea before coding

### 2. Fork & Branch
```bash
git checkout -b feature/your-feature-name
```

### 3. Make your changes
Keep it small and focused. One PR = one thing.

### 4. Open a Pull Request
Fill out the PR template. We'll review within 48 hours.

### Good First Issues
- Improve auto_categorizer keyword rules for English content
- Add domain entity extraction patterns to entity_linker.py
- Translate Chinese comments/docstrings to English
- Add more demo scenarios to seed_demo.py
- Improve test coverage for lifecycle_scanner

## Code Style

- Type hints (`from __future__ import annotations`)
- Google-style docstrings
- `logger` for logging, not `print`
- Keep functions small (< 50 lines preferred)

## Before Submitting

```bash
# Format
ruff check server/
ruff format server/

# Run tests
python -m pytest tests/ -v
```

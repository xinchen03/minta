#!/usr/bin/env python3
"""Backfill vector index for pre-existing context objects.

The write-side indexing hooks (services/vector_ops) only cover objects created
after deployment. Run this once to index the historical rows, so semantic
search (/api/search) covers the whole store. Idempotent (chroma upsert), safe
to re-run.

Usage (from repo root, with the server env active):

    D:/pycharm/anaconda/python.exe scripts/backfill_vectors.py \
        [--db-url sqlite:///./minta.db] [--limit 1000] [--dry-run]

Embedding model: MINTA_EMBEDDING_MODEL (default D:/all-mpnet-base-v2 local
dev; the Docker image sets it to the baked /models path).
"""
from __future__ import annotations

import argparse
import os
import sys
import time

_SERVER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "server")
if _SERVER not in sys.path:
    sys.path.insert(0, _SERVER)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db-url", default=os.environ.get("MINTA_DATABASE_URL", ""))
    ap.add_argument("--limit", type=int, default=0, help="0 = all rows")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-conflict", action="store_true",
                    help="skip the embedding_384 (conflict detection) pass")
    args = ap.parse_args()

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from models.context_object import ContextObject
    from services import vector_ops

    url = args.db_url
    if not url:
        # fall back to the server config default (same resolution as the app)
        from config import DATABASE_URL
        url = DATABASE_URL
    engine = create_engine(url, connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=engine)

    with Session() as db:
        q = db.query(ContextObject).filter(ContextObject.status != "archived")
        if args.limit > 0:
            q = q.limit(args.limit)
        rows = q.all()

    print(f"rows to index: {len(rows)} (dry_run={args.dry_run})")
    if args.dry_run:
        return

    t0 = time.time()
    done = skipped = 0
    for i, obj in enumerate(rows, 1):
        text = vector_ops.compose_text(obj.title, obj.summary, obj.body)
        if not text.strip():
            skipped += 1
            continue
        vector_ops.index_object(obj.id, text, obj.user_id, obj.type, obj.status)
        done += 1
        if i % 200 == 0:
            print(f"  {i}/{len(rows)} ({time.time() - t0:.0f}s)", flush=True)
    print(f"done: indexed={done} skipped_empty={skipped} "
          f"elapsed={time.time() - t0:.0f}s")

    # ── conflict pass: fill embedding_384 (never populated anywhere before) ──
    if not args.skip_conflict and not args.dry_run:
        from services import vector_ops as _vo

        print("filling conflict embeddings (MiniLM 384-d)...", flush=True)
        t1 = time.time()
        filled = 0
        with Session() as db2:
            objs = db2.query(ContextObject).filter(ContextObject.status != "archived").all()
            for j, o in enumerate(objs, 1):
                _vo.apply_conflict_embedding(o)
                if o.embedding_384:
                    filled += 1
                if j % 200 == 0:
                    db2.commit()
                    print(f"  {j}/{len(objs)} (filled {filled})", flush=True)
            db2.commit()
        print(f"conflict embeddings filled: {filled}/{len(objs)} "
              f"elapsed={time.time() - t1:.0f}s")


if __name__ == "__main__":
    main()

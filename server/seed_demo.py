"""Seed demo data for Minta public showcase.

Creates a realistic personal-assistant conversation history spanning 3 months,
with built-in memory quality issues: conflicts, stale facts, redundancies,
and fragmented information — all waiting to be discovered by Minta.

The story: "Alex, a startup founder using an AI coding assistant."
"""
from __future__ import annotations
import json
import os
import sys
import hashlib
import random
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Add server to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import SessionLocal, engine, Base
from models.context_object import ContextObject

Base.metadata.create_all(bind=engine)


def stable_id(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()[:12]


def _now_days_ago(days: int) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=days)
    return dt.isoformat()


# ── The Story: Alex's 3-month journey with an AI coding assistant ──
# Each entry is a "memory" the AI would store.
# We intentionally plant issues Minta should find.

DEMO_MEMORIES = [
    # === Month 1: Alex starts a new project ===
    {
        "title": "Project stack decision",
        "body": "Alex chose Next.js 14 for the frontend, with TypeScript and Tailwind CSS.",
        "type": "project_context",
        "created_at": _now_days_ago(90),
    },
    {
        "title": "Database choice",
        "body": "Alex decided to use PostgreSQL with Prisma ORM for the backend.",
        "type": "project_context",
        "created_at": _now_days_ago(90),
    },
    {
        "title": "Alex prefers concise answers",
        "body": "Alex told the AI: keep responses short, no more than 3 bullet points. Show code, not explanations.",
        "type": "preference",
        "created_at": _now_days_ago(88),
    },
    {
        "title": "Alex's coding style",
        "body": "Uses functional components, prefers arrow functions, names files in kebab-case, uses Zod for validation.",
        "type": "preference",
        "created_at": _now_days_ago(85),
    },
    {
        "title": "Auth provider",
        "body": "Alex chose NextAuth.js v5 with GitHub OAuth for authentication. No email/password login.",
        "type": "project_context",
        "created_at": _now_days_ago(80),
    },
    {
        "title": "Payment integration",
        "body": "Alex integrated Stripe for subscription payments. Monthly plan at $9.99, annual at $89.",
        "type": "project_context",
        "created_at": _now_days_ago(75),
    },

    # === ISSUE #1: CONFLICT — Alex changes auth strategy ===
    {
        "title": "Auth provider changed",
        "body": "Alex switched from NextAuth to Clerk. Removed NextAuth completely. Using Clerk's hosted pages.",
        "type": "project_context",
        "created_at": _now_days_ago(50),
    },
    # (This conflicts with entry #5 above — Minta should detect it!)

    # === ISSUE #2: STALE — Old technology choice still in memory ===
    {
        "title": "UI library v1",
        "last_used": _now_days_ago(88),
        "body": "Alex installed shadcn/ui v1.0 with the default theme. Using Card, Button, Dialog components.",
        "type": "project_context",
        "created_at": _now_days_ago(88),
    },
    {
        "title": "UI library v2",  # Updated 2 weeks ago, but old one still exists
        "body": "Alex upgraded to shadcn/ui v2.0. Migrated all components. Using new theming system with CSS variables.",
        "type": "project_context",
        "created_at": _now_days_ago(14),
    },

    # === ISSUE #3: REDUNDANCY — Same preference stated multiple ways ===
    {
        "title": "Meeting preference",
        "tags": ["meetings"],
        "body": "Alex prefers standups at 9:30 AM, no longer than 15 minutes. Async updates on Slack otherwise.",
        "type": "preference",
        "created_at": _now_days_ago(60),
    },
    {
        "title": "Standup time",
        "tags": ["meetings"],
        "body": "Daily standup is at 9:30 AM sharp. 15 minutes max. Slack if you can't make it.",
        "type": "preference",
        "created_at": _now_days_ago(58),
    },
    {
        "title": "Meeting format",
        "tags": ["meetings"],
        "body": "Alex wants meetings to be exactly 15 minutes, start at 9:30 AM, async on Slack preferred.",
        "type": "preference",
        "created_at": _now_days_ago(55),
    },
    # (Three nearly identical entries — Minta should flag as redundant!)

    # === ISSUE #4: FRAGMENTATION — Related info scattered across entries ===
    {
        "title": "Alex's team",
        "tags": ["team"],
        "body": "Team of 3: Alex (full-stack), Jordan (frontend), Sam (backend). All remote.",
        "type": "work_profile",
        "created_at": _now_days_ago(70),
    },
    {
        "title": "Jordan's expertise",
        "tags": ["team"],
        "body": "Jordan is the React specialist. 5 years experience. Owns all UI components and design system.",
        "type": "work_profile",
        "created_at": _now_days_ago(65),
    },
    {
        "title": "Sam's expertise",
        "tags": ["team"],
        "body": "Sam handles all backend and DevOps. PostgreSQL, Docker, AWS. On-call for production issues.",
        "type": "work_profile",
        "created_at": _now_days_ago(65),
    },
    {
        "title": "Alex's role",
        "tags": ["team"],
        "body": "Alex does full-stack. Handles auth, payments, and project management. Reviews all PRs.",
        "type": "work_profile",
        "created_at": _now_days_ago(60),
    },
    # (Team info scattered across 4 entries — Minta should suggest grouping!)

    # === Month 2-3: Normal evolution ===
    {
        "title": "Deployment platform",
        "body": "Alex deployed the app on Vercel with automatic preview deployments for each PR.",
        "type": "project_context",
        "created_at": _now_days_ago(40),
    },
    {
        "title": "Monitoring setup",
        "body": "Alex added Sentry for error tracking and Logtail for log management. PagerDuty for alerts.",
        "type": "project_context",
        "created_at": _now_days_ago(30),
    },
    {
        "title": "Alex's new preference",
        "body": "Alex now wants detailed explanations with examples. Changed from preferring short answers.",
        "type": "preference",
        "created_at": _now_days_ago(7),
    },
    # (This conflicts with entry #3 — Alex changed preference from short to detailed!)

    # === ISSUE #5: More staleness ===
    {
        "title": "API framework choice",
        "last_used": _now_days_ago(200),
        "body": "Alex chose Next.js API routes with tRPC for type-safe endpoints.",
        "type": "project_context",
        "created_at": _now_days_ago(200),
    },
    {
        "title": "API framework update",
        "body": "Alex migrated from tRPC to Hono. Deleted all tRPC routers. Using Hono with Zod validation.",
        "type": "project_context",
        "created_at": _now_days_ago(20),
    },

    # === Clean entries (no issues) ===
    {
        "title": "Git workflow",
        "body": "Alex uses trunk-based development. Feature branches merged within 2 days. Linear for issue tracking.",
        "type": "workflow",
        "created_at": _now_days_ago(60),
    },
    {
        "title": "Testing strategy",
        "body": "Vitest for unit tests, Playwright for E2E. 80% coverage target. CI runs on every PR.",
        "type": "project_context",
        "created_at": _now_days_ago(45),
    },
    {
        "title": "API rate limits",
        "body": "Alex set Stripe rate limits to 100 req/s for the API. Using Redis for rate limiting internally.",
        "type": "project_context",
        "created_at": _now_days_ago(35),
    },
]


def seed():
    db = SessionLocal()
    try:
        existing = db.query(ContextObject).count()
        if existing > 0:
            print(f"Database already has {existing} entries. Skipping seed.")
            print("To reset: delete server/minta.db and re-run.")
            return

        for i, mem in enumerate(DEMO_MEMORIES):
            obj = ContextObject(
                id=stable_id(mem["title"] + str(i)),
                user_id=1,
                source="document",
                title=mem["title"],
                body=mem["body"],
                type=mem["type"],
                status="active",
                confidence=4 + (i % 3),
                tags=mem.get("tags", []),
                created_at=datetime.fromisoformat(mem["created_at"]),
                updated_at=datetime.fromisoformat(mem["created_at"]),
                last_used_at=datetime.fromisoformat(mem.get("last_used", mem["created_at"])),
            )
            db.add(obj)

        db.commit()
        print(f"Seeded {len(DEMO_MEMORIES)} demo memories.")
        print()
        print("Story: Alex, a startup founder, uses an AI coding assistant for 3 months.")
        print()
        print("Planted issues Minta will detect:")
        print("  [!] CONFLICT: Auth changed NextAuth → Clerk (entries #5 vs #7)")
        print("  [!] CONFLICT: Alex changed from short→detailed answers (#3 vs #22)")
        print("  [STALE] STALE:   shadcn/ui v1.0 still in memory after v2.0 upgrade (#8)")
        print("  [STALE] STALE:   tRPC still in memory after Hono migration (#23)")
        print("  [REDUNDANT] REDUNDANT: 3 nearly identical standup preferences (#11-13)")
        print("  [REDUNDANT] FRAGMENTED: Team info across 4 entries (#14-17)")
        print()
        print("Run 'minta start' and visit http://localhost:8772 to see Minta find these.")

    except Exception as e:
        db.rollback()
        print(f"ERROR: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()

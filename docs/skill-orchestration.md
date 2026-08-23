# Skill Orchestration: Routing Capabilities Across Skill Sets

> Minta's own take on composing single-purpose skills into research workflows.
> The concrete routing table below is an **illustrative example** — Minta ships
> with the *pattern*, not a private configuration.

## The Problem

A research assistant needs many skills (search, reading, writing, figures,
compliance). Users should not have to know which skill handles what — and a
system should be able to *degrade gracefully* (primary fails → specialist
picks up → fallback covers).

## The Pattern: Capability Routing

Every capability is declared once, with three lanes:

```json
{
  "capabilities": {
    "literature_search": {
      "primary": "nature-academic-search",
      "specialist": "sas-literature:paper-lookup",
      "fallback": "sas-literature:paperzilla",
      "execution_lane": "reasoning-primary"
    },
    "citation_management": {
      "primary": "citation-management",
      "fallback": "sas-metaresearch:citation-management",
      "execution_lane": "reasoning-primary"
    }
  }
}
```

Semantics:
- **primary** — the default lane; usually the most specialized tool.
- **specialist** — narrower but deeper alternative when the primary is a poor fit.
- **fallback** — generic lane; only fires when primary and specialist both fail.
- **execution_lane** — `reasoning-primary` or `tool-primary`; tells the agent
  whether to reason first or act first.

## How Minta Uses It

- The local engine registers its own capabilities (memory search, compliance
  checking, expert inference) with `primary = minta <tool>` so the agent
  reaches high-quality memory without remembering MCP names.
- Third-party skill packs (Apache-2.0 companions, e.g.
  [nature-skills](https://github.com/Yuan1z0825/nature-skills)) register their
  capabilities alongside, typically as `primary` for *execution* lanes and
  `fallback` for research lanes.
- A `skill-registry.json` snapshot can be exported to audit what's installed
  and where it came from — useful for reproducible setups and CI checks.

## Design Rules

1. One capability, one row — never duplicate a capability across skills.
2. Prefer explicit names over inference: rows say *what* the lane does.
3. Fallback must be *generic*: if the fallback is as specialized as the
   primary, the row's ordering is wrong.
4. Registry and routing are data, not code: agents read them, they don't
   modify them.

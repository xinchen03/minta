// @xxinchen/dsh-plugin — Minta context quality layer for DeepSeek Harness.
//
// Two Cordis rows come from this bundle (see cordis.patch.yml):
//   - mcp-client-minta: official @deepseek-ai/dsh-mcp-client → Minta engine MCP
//   - minta-plugin:     this entry — runtime skill + session-start prewarm
//
// The engine is a separately deployed service (python minta_cli.py start).
// Loader contract (cordis-plugin-loader unwrapExports): the plugin is the
// DEFAULT export object { name, apply }.

const API_BASE = process.env.MINTA_API_URL ?? 'http://127.0.0.1:8772';

// Derived from the Minta interaction guide (docs/interaction-guide.md):
// hooks (automatic), commands (explicit), natural language (intent routing).
const SKILL_MEMORY_GOVERNANCE = {
  name: 'minta-memory-governance',
  description: 'Minta memory governance conventions and tool usage: read memory before answering about prior work, capture durable events after substantive turns, route correction signals to the inbox, never write silently.',
  whenToUse: 'When the session exposes mcp__minta__* tools and the user works on evolving research or project work.',
  invocation: { modelInvocable: true, userInvocable: true },
  content: [
    '## Minta memory governance',
    '',
    'Minta is a lifecycle-aware memory layer. If the mcp__minta__* tools are present, follow these conventions instead of keeping knowledge only in the conversation:',
    '',
    '**Before answering about prior work, past decisions, or project history**:',
    '1. Search first: call `minta_search_context` rather than asking the user to restate.',
    '2. For a named slot (e.g. a project or active experiment), call `minta_get_pack` to load the whole pack.',
    '3. If the engine suggests memory exists, call `minta_autopilot_preflight` so the loop read decision is logged.',
    '',
    '**After a substantive turn** (a decision, a new fact, a resolved conflict):',
    '4. Append a short entry with `minta_append_inbox`. Never write into the master memory directly — the user confirms from the inbox.',
    '5. When the user corrects you ("不对", "应该先…", "和上次的不一样"), treat it as a correction signal: this belongs in the inbox for the counter-example pipeline, and future behavior should change once confirmed.',
    '',
    '**Hygiene rules**:',
    '6. Redundancy ("这个和上次说的一样") → suggest a merge via the lifecycle scan rather than storing duplicates.',
    '7. If the engine is unreachable, say memory is unavailable — never fabricate remembered content.',
    '8. You propose, the user decides: the inbox is the only write path.',
    '',
    '**Expert domains**: for ankle/knee/cervical injury, ISO/prisma or compliance standards questions, call `minta_expert_infer` / `minta_expert_consult` so the domain engine (phase- and rule-aware) answers with calibrated confidence.',
  ].join('\n'),
};

export const name = 'minta';

async function prewarm(ctx) {
  // Engine health + recent memory overview. Fail-open: an unreachable engine
  // must never break a session.
  try {
    const status = await fetch(`${API_BASE}/api/autopilot/status`, {
      headers: { 'x-api-key': process.env.MINTA_API_KEY ?? '' },
    }).then((r) => r.json());
    const freshest = await fetch(`${API_BASE}/api/contextObjects/public?limit=5`).then((r) => r.json());
    const titles = Array.isArray(freshest)
      ? freshest.map((o) => o.title ?? o.id ?? '?').join(' | ')
      : '(no recent public memory)';
    ctx.logger?.info(
      `minta plugin: engine ${status.mode} (active=${status.active === true}); recent memory: ${titles}`,
    );
  } catch (error) {
    ctx.logger?.warn(`minta plugin: prewarm skipped (engine unreachable, fail-open): ${error?.message ?? error}`);
  }
}

export function apply(ctx) {
  // Runtime skills: register into the calling context's layer.
  const skills = ctx.get('skills');
  if (skills !== undefined && typeof skills.register === 'function') {
    try {
      skills.register(SKILL_MEMORY_GOVERNANCE);
    } catch (error) {
      ctx.logger?.warn(`minta plugin: skill registration failed: ${String(error)}`);
    }
  }

  // Session-start edge: rehydrate memory awareness before the first answer.
  ctx.on('agent/session-start', ({ agent }) => {
    ctx.logger?.info(`minta plugin: session-start for agent ${agent?.id ?? agent}`);
    void prewarm(ctx);
  });
}

export default { name, apply };

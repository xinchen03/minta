// Minta bundle entry — the MCP wiring lives in cordis.patch.yml (dsh.bundle.patch),
// which composes the mcp-client-minta row into the profile on install.
// No runtime plugin is needed: the Minta engine (separately deployed) carries the
// capabilities and is reached over streamable-http at 127.0.0.1:18721.
export const name = 'minta';

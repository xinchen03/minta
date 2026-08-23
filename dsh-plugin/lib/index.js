// Minta bundle entry — the minta MCP server is attached via dsh.mcpServers.
// This entry anchors the Cordis bundle; no runtime plugin is needed yet.
export const name = 'minta';
export function apply() { /* no-op: MCP server carries the capabilities */ }

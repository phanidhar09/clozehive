# Legacy Archive

These folders were moved here instead of deleted during the architecture cleanup.
The canonical ClozeHive runtime is now:

- `frontend`
- `services/api-gateway`
- `services/ai-agent`
- `services/mcp/*`

Archived folders:

- `backend/`: legacy Express + SQLite API with route prefixes that do not match the current `/api/v1` gateway contract.
- `ai-service/`: legacy monolithic FastAPI AI service superseded by `services/ai-agent` plus MCP tools.
- `fastapi-backend/`: earlier monolithic FastAPI backend superseded by `services/api-gateway`.
- `mcp-servers/`: earlier MCP server layout superseded by `services/mcp/*`.

Keep this archive until route parity, data migration, and production smoke tests are complete.

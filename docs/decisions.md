# Architecture Decision Log

- ADR-0001: P0 local-first and deterministic; optional LLM only in P1.
- ADR-0002: P0 defaults to suggestion-only; changes require a proven invariant check.
- ADR-0003: MCP capability, Skill workflow and optional Host Hook enforcement are separate concerns.
- ADR-0004: Protect project terminology and technical tokens before NLP.
- ADR-0005 (T-001): Pin `mcp==2.3.0` and adopt the **2.x API**: `mcp.server.mcpserver.MCPServer` replaces the v1 `FastMCP` (renamed upstream; import of `mcp.server.fastmcp` raises in 2.x). Verified live, not from stale examples.
- ADR-0006 (T-001): Pin `pythainlp==5.4.0`; verified `word_tokenize(engine='newmm')` runs with **zero downloads** under a fresh `HOME`, preserving the zero-outbound-network default (NFR-001). No corpus vendoring needed.

"""T-001 scaffold acceptance: package installs, imports, deps verified offline."""

import importlib.metadata as md


def test_package_imports() -> None:
    import thai_writing_mcp

    assert thai_writing_mcp.__version__


def test_pinned_dependency_versions() -> None:
    # Exact pins from pyproject.toml; validated against current official APIs.
    assert md.version("mcp") == "2.3.0"
    assert md.version("pythainlp") == "5.4.0"


def test_mcp_sdk_v2_api_surface() -> None:
    # mcp 2.x renamed FastMCP -> MCPServer (verified against 2.3.0, not stale v1 examples).
    from mcp.server.mcpserver import MCPServer

    server = MCPServer("thai-writing-quality")
    assert callable(server.tool)
    assert hasattr(server, "streamable_http_app")  # P1 transport


def test_pythainlp_newmm_offline(tmp_path, monkeypatch) -> None:
    # Fresh HOME => any corpus download would fail; newmm must tokenize from bundled data.
    monkeypatch.setenv("HOME", str(tmp_path))
    from pythainlp.tokenize import word_tokenize

    tokens = word_tokenize("ขออนุญาติ deploy API ไป production", engine="newmm")
    assert "deploy" in tokens and "API" in tokens
    assert not (tmp_path / ".pythainlp-data").exists()

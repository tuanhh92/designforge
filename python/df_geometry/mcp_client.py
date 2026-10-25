"""Thin, typed wrapper over the official `mcp` Python SDK (v2.x) for the forked SketchUp MCP server.

Transport is stdio: the agent spawns the server as a child process, so nothing listens on the network.
"""
from __future__ import annotations

import json
from contextlib import AsyncExitStack
from dataclasses import dataclass

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

REQUIRED_TOOLS = {"df_ping", "df_new_model", "df_execute_batch", "df_add_scenes", "df_export", "df_save", "df_model_stats"}


class SketchUpMcpError(RuntimeError):
    def __init__(self, tool: str, message: str, retryable: bool):
        super().__init__(f"{tool}: {message}")
        self.tool, self.retryable = tool, retryable


@dataclass(frozen=True)
class McpServerConfig:
    command: str                       # e.g. r"C:\designforge\venv\Scripts\python.exe"
    args: tuple[str, ...]              # ("-m", "sketchup_mcp.server")
    env: dict[str, str]                # {"DF_BRIDGE_PORT": "9876", "DF_BRIDGE_TOKEN": "...", "DF_ALLOW_EVAL": "0"}
    call_timeout_s: float = 120.0
    min_bridge_version: str = "0.2.0"


class McpSketchUpClient:
    def __init__(self, cfg: McpServerConfig):
        self.cfg = cfg
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None
        self.bridge_info: dict = {}

    async def __aenter__(self) -> "McpSketchUpClient":
        self._stack = AsyncExitStack()
        try:
            return await self._connect()
        except BaseException:
            # __aexit__ is not called when __aenter__ raises: close the stdio task group here or it hangs.
            await self._stack.aclose()
            raise

    async def _connect(self) -> "McpSketchUpClient":
        assert self._stack is not None
        params = StdioServerParameters(command=self.cfg.command, args=list(self.cfg.args), env=self.cfg.env)
        read, write = await self._stack.enter_async_context(stdio_client(params))
        self._session = await self._stack.enter_async_context(ClientSession(read, write))
        await self._session.initialize()
        tools = {t.name for t in (await self._session.list_tools()).tools}
        missing = REQUIRED_TOOLS - tools
        if missing:
            raise SketchUpMcpError("handshake", f"server missing tools {sorted(missing)}", retryable=False)
        if "eval_ruby" in tools and self.cfg.env.get("DF_ALLOW_EVAL") != "1":
            raise SketchUpMcpError("handshake", "eval_ruby exposed in production build", retryable=False)
        self.bridge_info = await self.call("df_ping", {})
        return self

    async def __aexit__(self, *exc) -> None:
        if self._stack:
            await self._stack.aclose()

    async def call(self, tool: str, args: dict) -> dict:
        assert self._session, "use `async with`"
        result = await self._session.call_tool(tool, arguments=args, read_timeout_seconds=self.cfg.call_timeout_s)
        payload = _unwrap(result.structured_content) or _first_text_json(result.content)
        if result.is_error or payload.get("ok") is False:
            message = payload.get("error") or payload.get("text") or "unknown error"
            raise SketchUpMcpError(tool, message, bool(payload.get("retryable", False)))
        return payload


def _unwrap(structured: dict | None) -> dict | None:
    """MCP servers wrap non-object return values as {"result": ...}; our tools return objects."""
    if structured and set(structured) == {"result"} and isinstance(structured["result"], dict):
        return structured["result"]
    return structured


def _first_text_json(content) -> dict:
    for block in content:
        if getattr(block, "type", None) == "text":
            try:
                return json.loads(block.text)
            except json.JSONDecodeError:
                return {"ok": True, "text": block.text}
    return {"ok": True}

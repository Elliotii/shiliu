from __future__ import annotations

from typing import Any

CONTEXT7_URL = "https://mcp.context7.com/mcp"
CONTEXT7_ALLOWED_TOOLS = frozenset({"resolve-library-id", "query-docs"})
CONTEXT7_TOOL_NAME_MAP = {
    "context7_resolve_library_id": "resolve-library-id",
    "context7_query_docs": "query-docs",
}


class Context7MCPClient:
    def __init__(
        self,
        *,
        url: str = CONTEXT7_URL,
        bearer_token: str | None = None,
        response_limit: int = 1_048_576,
    ) -> None:
        self.url = url
        self.bearer_token = bearer_token
        self.response_limit = response_limit
        self._client: Any = None
        self._http: Any = None
        self.tools: dict[str, dict[str, Any]] = {}

    async def connect(self) -> None:
        if self._client is not None:
            return
        from mcp import Client
        from mcp.client.streamable_http import streamable_http_client

        transport: Any = self.url
        if self.bearer_token:
            import httpx2

            self._http = httpx2.AsyncClient(
                headers={"Authorization": f"Bearer {self.bearer_token}"}
            )
            await self._http.__aenter__()
            transport = streamable_http_client(self.url, http_client=self._http)
        client = Client(transport, read_timeout_seconds=30)
        try:
            await client.__aenter__()
            tools: dict[str, dict[str, Any]] = {}
            cursor: str | None = None
            while True:
                page = await client.list_tools(cursor=cursor, cache_mode="bypass")
                for tool in page.tools:
                    if tool.name in CONTEXT7_ALLOWED_TOOLS:
                        tools[tool.name] = tool.model_dump(mode="json")
                cursor = getattr(page, "next_cursor", None)
                if not cursor:
                    break
            missing = CONTEXT7_ALLOWED_TOOLS - set(tools)
            if missing:
                raise RuntimeError(f"context7_tool_schema_missing:{sorted(missing)}")
        except Exception:
            await client.__aexit__(None, None, None)
            if self._http is not None:
                await self._http.__aexit__(None, None, None)
                self._http = None
            raise
        self._client = client
        self.tools = {
            exposed: tools[remote]
            for exposed, remote in CONTEXT7_TOOL_NAME_MAP.items()
        }

    async def call(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if self._client is None:
            raise RuntimeError("context7_not_connected")
        if tool_name not in self.tools:
            raise ValueError("context7_tool_not_allowed")
        result = await self._client.call_tool(CONTEXT7_TOOL_NAME_MAP[tool_name], arguments)
        payload = result.model_dump(mode="json")
        encoded = str(payload).encode("utf-8")
        if len(encoded) > self.response_limit:
            raise RuntimeError("context7_response_too_large")
        if bool(payload.get("isError") or payload.get("is_error")):
            raise RuntimeError("context7_tool_error")
        return payload

    async def close(self) -> None:
        if self._client is not None:
            await self._client.__aexit__(None, None, None)
            self._client = None
        if self._http is not None:
            await self._http.__aexit__(None, None, None)
            self._http = None
        self.tools = {}

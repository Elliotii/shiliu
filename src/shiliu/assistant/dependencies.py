from __future__ import annotations

import fcntl
import gc
import os
from pathlib import Path
from typing import Any


MEM0_MODEL = "BAAI/bge-small-zh-v1.5"
MEM0_DIMS = 512
MEM0_INDEX_GENERATION = "mem0-2.1.0-fastembed-bge-small-zh-v1.5-512-v1"
CONTEXT7_URL = "https://mcp.context7.com/mcp"
CONTEXT7_ALLOWED_TOOLS = frozenset({"resolve-library-id", "query-docs"})
CONTEXT7_TOOL_NAME_MAP = {
    "context7_resolve_library_id": "resolve-library-id",
    "context7_query_docs": "query-docs",
}


class AssistantProcessLock:
    """One serve process owns the embedded Qdrant directory."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._handle: Any = None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            handle.close()
            raise RuntimeError("assistant_index_already_owned") from exc
        self._handle = handle

    def release(self) -> None:
        if self._handle is None:
            return
        fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        self._handle.close()
        self._handle = None


class Mem0SemanticIndex:
    """Thin, local-only Mem0 owner used by Stage A live verification."""

    def __init__(self, state_dir: Path) -> None:
        self.state_dir = state_dir.resolve()
        self._memory: Any = None
        self._lock = AssistantProcessLock(self.state_dir / "owner.lock")

    def start(self) -> None:
        if self._memory is not None:
            return
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._lock.acquire()
        try:
            os.environ["FASTEMBED_CACHE_PATH"] = str(self.state_dir / "model-cache")
            os.environ["MEM0_TELEMETRY"] = "False"
            from mem0 import Memory

            self._memory = Memory.from_config(
                {
                    "vector_store": {
                        "provider": "qdrant",
                        "config": {
                            "collection_name": "shiliu_assistant_memories",
                            "embedding_model_dims": MEM0_DIMS,
                            "path": str(self.state_dir / "qdrant"),
                            "on_disk": True,
                        },
                    },
                    "embedder": {
                        "provider": "fastembed",
                        "config": {"model": MEM0_MODEL, "embedding_dims": MEM0_DIMS},
                    },
                    # infer=False never calls this endpoint. It is explicit and loopback-only
                    # so the library cannot silently select a remote default model.
                    "llm": {
                        "provider": "openai",
                        "config": {
                            "model": "unused-infer-false",
                            "api_key": "unused-infer-false",
                            "openai_base_url": "http://127.0.0.1:1/v1",
                        },
                    },
                    "history_db_path": ":memory:",
                    "version": "v1.1",
                }
            )
        except Exception:
            self._lock.release()
            raise

    def add(
        self,
        text: str,
        *,
        record_id: str,
        operation_id: str,
        record_version: int = 1,
        scope_key: str = "user",
    ) -> dict[str, Any]:
        memory = self._require_started()
        result = memory.add(
            text,
            user_id="local_operator",
            agent_id="shiliu_assistant_memory",
            metadata={
                "record_id": record_id,
                "record_version": record_version,
                "scope_key": scope_key,
                "index_generation": MEM0_INDEX_GENERATION,
                "operation_id": operation_id,
            },
            infer=False,
        )
        return dict(result)

    def search(
        self, query: str, *, top_k: int = 5, scope_key: str = "user"
    ) -> list[dict[str, Any]]:
        memory = self._require_started()
        result = memory.search(
            query,
            top_k=top_k,
            filters={
                "user_id": "local_operator",
                "agent_id": "shiliu_assistant_memory",
                "scope_key": scope_key,
                "index_generation": MEM0_INDEX_GENERATION,
            },
        )
        values = result.get("results", result) if isinstance(result, dict) else result
        return [dict(item) for item in values]

    def get_all(self, *, scope_key: str) -> list[dict[str, Any]]:
        memory = self._require_started()
        result = memory.get_all(
            filters={
                "user_id": "local_operator",
                "agent_id": "shiliu_assistant_memory",
                "scope_key": scope_key,
                "index_generation": MEM0_INDEX_GENERATION,
            }
        )
        values = result.get("results", result) if isinstance(result, dict) else result
        return [dict(item) for item in values]

    def delete(self, backend_id: str) -> None:
        self._require_started().delete(backend_id)

    def stop(self) -> None:
        memory = self._memory
        self._memory = None
        try:
            if memory is not None:
                vector_store = getattr(memory, "vector_store", None)
                client = getattr(vector_store, "client", None)
                if client is not None and hasattr(client, "close"):
                    client.close()
                if hasattr(memory, "close"):
                    memory.close()
        finally:
            # FastEmbed owns native ONNX resources.  Collect while Python and
            # libc++ are still fully alive instead of leaving them to interpreter
            # teardown, which can abort an otherwise successful init command.
            del memory
            gc.collect()
            self._lock.release()

    def _require_started(self) -> Any:
        if self._memory is None:
            raise RuntimeError("semantic_index_not_started")
        return self._memory


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

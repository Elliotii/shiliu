import json
from types import SimpleNamespace
import pytest
from shiliu.ask.deep.v2 import V2Decision, QueryReduction
from test_v4_fast_ask_api import _application, _Provider

@pytest.fixture
def formal(app_paths, monkeypatch):
    # Historical SQLite fixture; keep its removed dependencies out of PG tests.
    from shiliu.retrieval.dense import SQLiteExactDenseIndex, provider_identity
    from test_dense_retrieval import FakeEmbeddingProvider
    class Embedding(FakeEmbeddingProvider):
        def model_identity(self): return provider_identity(FakeEmbeddingProvider())
    monkeypatch.setenv('SHILIU_DEEP_V2_TRACE_DIR', str(app_paths.logs_dir / 'deep'))
    class Provider(_Provider):
        def generate_structured(self, **kw):
            if kw['role'] == 'agent_action':
                self.agent_calls += 1
                data = ({'type':'continue','actions':[{'action_id':'a','kind':'search_transcripts',
                    'arguments':{'query':'MCP'},'purpose':'answer'}]} if self.agent_calls == 1
                    else {'type':'finish','outcome':'sufficient','finish_reason':'done'})
                return SimpleNamespace(output=V2Decision.model_validate(data), usage={})
            if kw['role'] == 'query_reduce':
                c=json.loads(kw['messages'][-1]['content'])['candidates']
                data={'sufficient':bool(c),'findings':[{'subject':'MCP','text':'协议连接工具',
                    'evidence_refs':[c[0]['evidence_ref']]}] if c else [],'unresolved':[]}
                return SimpleNamespace(output=QueryReduction.model_validate(data),usage={})
            if kw["role"] == "grounded_answer": kw["max_tokens"] = 8192
            return super().generate_structured(**kw)
    provider=Provider()
    core,raw=_application(app_paths,provider,claim_verifier=None)
    core.deep_v2_provider=lambda role:provider
    core.deep_v2_answer_provider=lambda role:provider
    core.fast_answer_provider=lambda role:provider
    core._dense_retrieval=SQLiteExactDenseIndex(db=core.db,provider=Embedding())
    core._dense_retrieval.rebuild()
    with core.db.connect() as db:db.execute("UPDATE retrieval_sync_state SET dense_state='current'")
    core._ask_service=None
    return core,provider,raw


@pytest.fixture
def pg_formal(app_paths, monkeypatch, tmp_path):
    """Current product composition in a guarded random PostgreSQL child DB."""
    import os
    from dataclasses import replace
    from pathlib import Path
    from shiliu.app import Application
    from shiliu.config import AppConfig, PostgresConfig
    from schema_support import formal_target
    from test_collection_retrieval import FixedProvider, add_video

    monkeypatch.setenv('SHILIU_DEEP_V2_TRACE_DIR', str(app_paths.logs_dir / 'deep'))
    class StreamingProvider(_Provider):
        supports_answer_streaming = True

        def generate_structured(self, **kwargs):
            on_content = kwargs.pop('on_content', None)
            kwargs.pop('on_reset', None)
            response = super().generate_structured(**kwargs)
            if on_content is not None:
                content = response.output.model_dump_json()
                midpoint = len(content) // 2
                on_content(content[:midpoint])
                on_content(content[midpoint:])
            return response

    provider = StreamingProvider()
    control = PostgresConfig(os.environ['SHILIU_DATABASE_URL'],
        Path(os.environ['SHILIU_ARTIFACT_ROOT']), 'test')
    with formal_target(control) as (runtime, _):
        artifact_root = tmp_path / 'formal-artifacts'
        artifact_root.mkdir(mode=0o700)
        core = Application(app_paths,
            config=AppConfig(content_dir=str(app_paths.content_dir), assistant_enabled=False),
            postgres_config=replace(runtime, artifact_root=artifact_root),
            embedding_provider=FixedProvider(), adapter=object(),
            provider_factory=lambda role: provider,
            provider_availability=lambda: {'available': False, 'reason': 'synthetic offline'})
        try:
            core.deep_v2_provider = lambda role: provider
            core.deep_v2_answer_provider = lambda role: provider
            core.fast_answer_provider = lambda role: provider
            resources = (core.db, core.artifacts, core.retrieval, core.dense_retrieval)
            _, vid = add_video(resources, text='MCP 通过协议连接模型与外部工具。')
            core.dense_retrieval.rebuild()
            raw = core.db.get_video(vid)['raw_subtitle_path']
            yield core, provider, raw
        finally:
            core.close()

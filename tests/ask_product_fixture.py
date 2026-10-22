import json
from types import SimpleNamespace
import pytest
from shiliu.ask.deep.v2 import V2Decision, QueryReduction
from shiliu.retrieval.dense import SQLiteExactDenseIndex, provider_identity
from test_dense_retrieval import FakeEmbeddingProvider
from test_v4_fast_ask_api import _application, _Provider

class Embedding(FakeEmbeddingProvider):
    def model_identity(self): return provider_identity(FakeEmbeddingProvider())

@pytest.fixture
def formal(app_paths, monkeypatch):
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

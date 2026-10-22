"""Test setup for the active context entry, with real storage and dependency checks."""
import asyncio

from shiliu.artifacts import ArtifactStore
from shiliu.assistant.sources import CollectionSourceService
from shiliu.assistant.snapshots import SourceSnapshotStore
from shiliu.assistant.store import AssistantRunStore
from shiliu.assistant.task_notes import TaskNoteService
from shiliu.assistant.tools import AssistantToolRegistry
from shiliu.assistant.wiki import WikiService
from shiliu.assistant.provider import OpenAICompatibleAssistantProvider
from shiliu.assistant.working_context import WorkingContextComposer


class ContextHarness:
    def __init__(self, memories, *, tools=None, task_notes=None, input_budget_tokens=256000):
        self.store = AssistantRunStore(memories.db)
        if tools is None:
            # Matches this suite's app_paths fixture, without loading user settings.
            content = memories.db.path.parent.parent / 'content'
            artifacts = ArtifactStore(content / 'videos')
            sources = CollectionSourceService(db=memories.db, artifacts=artifacts,
                snapshots=SourceSnapshotStore(memories.db, artifacts, content / 'assistant'))
            tools = AssistantToolRegistry(store=self.store, memories=memories, sources=sources,
                wiki=WikiService(db=memories.db, store=self.store, sources=sources))
        self.notes = task_notes or TaskNoteService(memories.db, memories,
            source_ref_validator=lambda refs, sid: tools.dependency_refs_valid(
                refs, sid, self.thread_id, self.scope_version),
            dependency_ref_validator=tools.dependency_refs_valid)
        self.composer = WorkingContextComposer(store=self.store, tools=tools, task_notes=self.notes)
        self.composer.input_budget_tokens = input_budget_tokens
        self.provider = OpenAICompatibleAssistantProvider(base_url='https://api.deepseek.com/v1',
            model='deepseek-v4-flash', api_key='synthetic')
        self.candidate = None

    def request_input(self, context, *, tool_schemas=None):
        run = self.store.get_run(context['run']['id'])
        if run['status'] == 'queued':
            claimed = self.store.claim_next_run()
            assert claimed and claimed['id'] == run['id']
        self.thread_id = context['thread']['id']
        self.scope_version = context['space']['scope_version']
        self.candidate = self.composer.prepare(run['id'], provider=self.provider, tool_schemas=tool_schemas)
        return self.candidate.request.body['messages'], self.candidate.request.input_tokens, self.candidate.metadata

    def request_messages(self, context, **kwargs):
        messages, tokens, _ = self.request_input(context, **kwargs)
        return messages, tokens


def mixed_checkpoint(c3, *, personal='面试演示架构采用 Redis', kind='decision'):
    """Real Runtime checkpoint fixture; the supplied summary is a synthetic model reply."""
    from test_assistant_context_c3 import history
    memory = c3.memories.save_explicit(text=personal, subject_key='mixed-context', kind=kind,
        pinned=True, scope_kind='space', scope_id=c3.space['id'], operation_key='mixed-memory')
    run, state, _ = history(c3)
    c3.store.save_task_focus(run['id'], epoch=run['run_epoch'], focus={
        'goal':'完整阅读两份材料后比较条件', 'requirements':['本轮只分析，不保存'],
        'working_notes':'独立材料说明适用条件；独立知识页', 'next_actions':['继续读第二份材料']})
    c3.provider.summary = personal + '；独立核对摘要：条件未知，不能据交付认定已完成。'
    candidate = asyncio.run(c3.graph._prepare_dispatch(state, provider=c3.provider))
    assert candidate.checkpoint
    assert c3.store.complete_run(run['id'], epoch=run['run_epoch'], answer='独立阶段结果', usage={})
    return memory, candidate


def deliver_collection(store, registry, run, source_ref, *, view='summary'):
    """Run the production read/prepare/send/confirm path, using offline transport."""
    from shiliu.assistant.provider import ModelTurn, NativeToolCall
    from shiliu.assistant.runtime import AssistantExecutionGraph
    from assistant_offline_provider import offline_provider

    class Reader:
        def __init__(self):
            self.calls = 0

        def turn(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return ModelTurn('', [NativeToolCall('deliver-source', 'collection_read',
                    {'source_ref': source_ref, 'view': view})])
            return ModelTurn('已读取材料正文。')

    provider = offline_provider(Reader())
    graph = AssistantExecutionGraph(store=store, memories=registry.memories, tools=registry,
                                    provider_factory=lambda: provider)
    asyncio.run(graph.run(run))
    completed = store.get_run(run['id'])
    assert completed['status'] == 'completed', completed
    assert any(m.get('source_ref') == source_ref and m.get('view') == view
               and m.get('kind') == 'collection_read'
               for m in completed['working_state'].get('model_delivered_materials', []))

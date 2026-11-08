"""Content-contract identity checks; no database, network or model calls."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from shiliu.assistant.context import SYSTEM_RULES
from shiliu.assistant.task_notes import TaskNoteService
from shiliu.assistant.tools import AssistantToolRegistry
from shiliu.assistant.working_context import context_identity


def registry():
    return AssistantToolRegistry(sources=None, memories=None, store=None, wiki=object())


@pytest.mark.parametrize("changed", ["system", "tool_description"])
def test_contract_change_rejects_old_checkpoint_without_changing_note(changed):
    tools = registry()
    space = {"task_subset": None}
    identity_tools = SimpleNamespace(scope_identity=lambda _: {"scope": "synthetic"})
    schemas = tools.schemas()
    old = context_identity(identity_tools, space, "synthetic", tool_schemas=schemas)
    assert old == context_identity(identity_tools, space, "synthetic", tool_schemas=schemas)
    updated = deepcopy(schemas)
    rules = SYSTEM_RULES
    if changed == "system":
        rules += "\nsynthetic changed contract"
    else:
        save = next(t for t in updated if t["function"]["name"] == "knowledge_save_request")
        save["function"]["description"] += " synthetic changed contract"
    new = context_identity(identity_tools, space, "synthetic", system_rules=rules, tool_schemas=updated)
    assert old["contract"] != new["contract"]
    assert {k: v for k, v in old.items() if k != "contract"} == {
        k: v for k, v in new.items() if k != "contract"}

    note = {"checkpoint": {"format_version": 1, "identity": old, "text": "old note"}}
    before = deepcopy(note)
    # Exercise the production rejection branch. A mismatched contract must not
    # consult storage or mutate/delete the original note.
    service = TaskNoteService.__new__(TaskNoteService)
    service.valid_for_context = lambda *args, **kwargs: note
    assert service.checkpoint_for_context("thread", space_id=1, scope_version=1, identity=new) is None
    assert note == before

"""P3 import/retirement checks, without constructing default Application."""

import subprocess
import sys

import pytest


def test_p3_imports_never_load_retired_vector_backends():
    code = """
import sys
class RefuseLegacy:
    def find_spec(self,name,path=None,target=None):
        if name.split('.')[0] in {'mem0','fastembed','qdrant_client','onnxruntime'}:
            raise AssertionError('Retired vector backend import: '+name)
sys.meta_path.insert(0,RefuseLegacy())
import shiliu.assistant.memory
import shiliu.assistant.wiki
import shiliu.assistant.wiki_jobs
import shiliu.assistant.runtime
import shiliu.cli
assert not any(n.split('.')[0] in {'mem0','fastembed','qdrant_client'} for n in sys.modules)
"""
    subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    )


def test_retired_memory_initializer_is_fail_closed_without_default_paths(
    monkeypatch, capsys
):
    from shiliu.cli import initialize_assistant_memory
    from shiliu.config import AppPaths

    def denied(*args, **kwargs):
        raise AssertionError("Daily paths must not be read")

    monkeypatch.setattr(AppPaths, "defaults", denied)
    assert initialize_assistant_memory() == 2
    assert "retired" in capsys.readouterr().out


def test_incomplete_runtime_store_does_not_start_any_legacy_backend():
    from shiliu.assistant.runtime import AssistantRuntime

    with pytest.raises(RuntimeError, match="requires_W10"):
        AssistantRuntime(
            store=object(), sources=None, context7=None, provider_factory=lambda: None
        )

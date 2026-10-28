"""Explicit P4 rerun of the retained tiny pinned-model semantic case set."""
from pathlib import Path
import local_qwen_p3_cases as original
from test_wiki import wiki_parts  # noqa: F401


def test_p4_offline_memory_and_wiki_cases(wiki_parts,monkeypatch):  # noqa: F811
    previous=Path('/tmp/shiliu-w01-20261023/p3-qwen-author-final-cases.json')
    current=Path('/private/tmp/shiliu-w01-20261023/p4-qwen-cases.json')
    def output_path(value):
        return current if Path(value)==previous else Path(value)
    monkeypatch.setattr(original,'Path',output_path)
    original.test_offline_memory_and_wiki_chinese_cases(wiki_parts)

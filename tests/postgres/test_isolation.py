from dataclasses import replace
from pathlib import Path

import pytest

from shiliu.config import PostgresConfig
from isolation import TASK_ROOT, guard


@pytest.mark.parametrize('change', [
    {'environment': 'production'},
    {'database_url': 'host=localhost port=5432 dbname=shiliu_w01_test_fake user=shiliu_w01_runtime'},
    {'database_url': f'host={TASK_ROOT}/socket port=55483 dbname=my_test user=shiliu_w01_runtime'},
    {'database_url': f'host={TASK_ROOT}/socket port=55483 dbname=shiliu_w01_test_safe user=unknown'},
    {'database_url': f'host={TASK_ROOT}/socket port=55483 dbname=shiliu_w01_test_safe user=shiliu_w01_runtime options=PRIVATE'},
    {'artifact_root': Path('/tmp/daily-content')},
])
def test_refuses_unknown_targets_before_connect(change):
    cfg = PostgresConfig(f'host={TASK_ROOT}/socket port=55483 dbname=shiliu_w01_test_safe user=shiliu_w01_runtime',
                         TASK_ROOT / 'artifacts', 'test')
    with pytest.raises(ValueError, match='Refusing') as caught:
        guard(replace(cfg, **change))
    assert 'PRIVATE' not in str(caught.value)


def test_refuses_ambient_libpq_redirect_before_connect(monkeypatch):
    cfg = PostgresConfig(f'host={TASK_ROOT}/socket port=55483 dbname=shiliu_w01_test_safe user=shiliu_w01_runtime',
                         TASK_ROOT / 'artifacts', 'test')
    monkeypatch.setenv('PGHOSTADDR', '127.0.0.1')
    with pytest.raises(ValueError, match='Refusing'):
        guard(cfg)

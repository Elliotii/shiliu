from dataclasses import FrozenInstanceError
from datetime import date, datetime, timezone
from pathlib import Path
import os
import subprocess
import sys

import pytest

from shiliu.config import PostgresConfig, load_postgres_config
from shiliu.storage.dto import row_dto
from shiliu.storage.scope import personal_context


@pytest.mark.parametrize('dsn', ['', 'sqlite:///daily.db', 'postgresql://u:PRIVATE@[broken/db',
                                 "host=localhost dbname=test user=u invalid=PRIVATE", "dbname=test"])
def test_config_fails_without_exposing_dsn(dsn, tmp_path):
    with pytest.raises(ValueError) as caught:
        PostgresConfig(dsn, tmp_path, 'test')
    assert 'PRIVATE' not in str(caught.value)
    assert caught.value.__cause__ is None


def test_explicit_loader_and_repr(monkeypatch, tmp_path):
    for key in ('SHILIU_DATABASE_URL', 'SHILIU_ARTIFACT_ROOT', 'SHILIU_ENV'):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(ValueError):
        load_postgres_config()
    path = tmp_path / 'config.toml'
    path.write_text('[postgres]\ndatabase_url="host=localhost dbname=example user=u password=PRIVATE"\n'
                    f'artifact_root="{tmp_path}"\nenvironment="development"\n')
    cfg = load_postgres_config(path)
    assert 'PRIVATE' not in repr(cfg) and 'database_url' not in repr(cfg)
    monkeypatch.setenv('SHILIU_ENV', 'test')
    assert load_postgres_config(path).environment == 'test'
    path.write_text('password="PRIVATE"\ninvalid = [')
    with pytest.raises(ValueError, match='Cannot read') as caught:
        load_postgres_config(path)
    assert 'PRIVATE' not in str(caught.value)
    with pytest.raises(ValueError):
        PostgresConfig('host=localhost dbname=test user=u', Path('relative'), 'test')
    with pytest.raises(ValueError):
        PostgresConfig('host=localhost dbname=test user=u', tmp_path, 'unknown')


def test_dto_is_explicit():
    raw = {'id': 8, 'flag': True, 'json': {'null': None, 'ordered': [3, 1, 2]},
           'text': '[1,2]', 'at': datetime(2026, 10, 23, tzinfo=timezone.utc),
           'day': date(2026, 10, 23), 'empty': None}
    out = row_dto(raw, timestamps=('at', 'absent', 'empty'), dates=('day',))
    assert out['at'] == '2026-10-23T00:00:00+00:00'
    assert out['day'] == '2026-10-23'
    assert out['json'] is raw['json'] and out['text'] == '[1,2]'
    assert type(out['id']) is int and type(out['flag']) is bool
    assert 'absent' not in out and out['empty'] is None
    with pytest.raises(ValueError):
        row_dto({'at': datetime(2026, 1, 1)}, timestamps=('at',))
    with pytest.raises(FrozenInstanceError):
        personal_context().user_id = 'client'


def test_import_does_not_connect_or_read_default_paths():
    result = subprocess.run([sys.executable, '-c', '''
import sys
def audit(event, args):
    if event in {'socket.__new__', 'socket.connect'}:
        raise AssertionError('socket')
sys.addaudithook(audit)
from shiliu.config import AppPaths
AppPaths.defaults = lambda: (_ for _ in ()).throw(AssertionError('daily paths'))
import shiliu.storage.scope
import shiliu.storage.dto
'''], capture_output=True, text=True, timeout=10, env=dict(os.environ))
    assert result.returncode == 0, result.stderr

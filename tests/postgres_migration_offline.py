"""Opt-in safety plugin: pytest -p postgres_migration_offline (W00 selection only)."""
from pathlib import Path
import socket
import sqlite3
import subprocess
import tempfile
from urllib.parse import unquote

import pytest


@pytest.fixture(autouse=True)
def w00_offline_boundary(monkeypatch):
    from shiliu.app import Application
    from shiliu.config import AppPaths
    import keyring
    import shiliu.config

    def forbidden(*args, **kwargs):
        raise AssertionError('W00 forbids Application/default paths/credentials/network')

    original_connect = sqlite3.connect
    roots = (Path(tempfile.gettempdir()).resolve(), Path('/tmp').resolve())

    def temporary_connect(database, *args, **kwargs):
        value = str(database)
        if value != ':memory:':
            if value.startswith('file:'):
                value = unquote(value[5:].split('?', 1)[0])
            path = Path(value).resolve()
            if not path.is_absolute() or not any(path.is_relative_to(root) for root in roots):
                raise AssertionError(f'W00 SQLite must be synthetic and temporary: {path}')
        return original_connect(database, *args, **kwargs)

    monkeypatch.setattr(sqlite3, 'connect', temporary_connect)
    monkeypatch.setattr(Application, '__init__', forbidden)
    monkeypatch.setattr(AppPaths, 'defaults', forbidden)
    monkeypatch.setattr(shiliu.config, 'load_api_key', forbidden)
    monkeypatch.setattr(keyring, 'get_password', forbidden)
    monkeypatch.setattr(keyring, 'get_credential', forbidden)
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket.socket, 'connect_ex', forbidden)
    monkeypatch.setattr(socket, 'getaddrinfo', forbidden)
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    monkeypatch.setenv('HF_HUB_OFFLINE', '1')
    monkeypatch.setenv('TRANSFORMERS_OFFLINE', '1')

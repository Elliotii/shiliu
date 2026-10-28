"""Explicit input ownership; never rewrites/merges an existing principal ID."""
from __future__ import annotations
import json
import re
from shiliu.migration.values import MigrationRejected

DEFAULT_SYNTHETIC = {'default_principal':'local_operator',
    'principals':{'local_operator':'personal:local_operator'}}


def load_ownership(path, *, synthetic):
    if not path.exists():
        if not synthetic:raise MigrationRejected('explicit_principal_mapping_required')
        return DEFAULT_SYNTHETIC
    if path.is_symlink():raise MigrationRejected('unsafe_ownership_manifest')
    value=json.loads(path.read_text())
    if set(value)!={'default_principal','principals'} or not isinstance(value['principals'],dict):
        raise MigrationRejected('invalid_ownership_manifest')
    if value['default_principal'] not in value['principals']:
        raise MigrationRejected('unmapped_default_principal')
    for owner,workspace in value['principals'].items():
        if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}',owner) or workspace!='personal:'+owner:
            raise MigrationRejected('invalid_personal_workspace_mapping')
    return value


def owner_for(identity,row):
    value=identity['ownership']
    owner=row.get('principal_id',value['default_principal'])
    if owner not in value['principals']:raise MigrationRejected('explicit_principal_mapping_required')
    return owner,value['principals'][owner]


def artifact_workspace(identity,descriptor):
    owner=descriptor.get('principal_id',identity['ownership']['default_principal'])
    if owner not in identity['ownership']['principals']:raise MigrationRejected('unmapped_artifact_owner')
    workspace=identity['ownership']['principals'][owner]
    if not descriptor['relative_key'].startswith(workspace+'/'):
        raise MigrationRejected('artifact_workspace_key_mismatch')
    return workspace

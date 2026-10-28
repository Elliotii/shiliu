"""Column-typed migration values. JSON text, SQL NULL and byte hashes stay distinct."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date,datetime,timezone
import hashlib
import json
import math
from typing import Any


class MigrationRejected(RuntimeError):
    """Public category only; input IDs stay in the private migration ledger."""
    def __init__(self,category,*,table_name='__run__',record_key=None):
        self.table_name=table_name
        self.record_key=record_key or {}
        super().__init__(category)


@dataclass(frozen=True)
class JsonDocument:
    value: Any


def strict_json(text):
    try:
        if type(text) is not str:raise ValueError()
        result=json.loads(text,parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        json.dumps(result,allow_nan=False)
        return result
    except (ValueError,TypeError):raise MigrationRejected('invalid_json') from None


def convert(value,definition,*,field: str):
    if value is None:
        if not definition['nullable']:raise MigrationRejected('null_required_column')
        return None
    typ=definition['type']
    if typ=='jsonb':return JsonDocument(strict_json(value))
    if typ=='boolean':
        if type(value) not in {int,bool} or value not in (0,1):raise MigrationRejected('invalid_boolean')
        return bool(value)
    if typ in {'bigint','integer'}:
        if type(value) is not int:raise MigrationRejected('invalid_integer')
        if not -(2**63)<=value<2**63:raise MigrationRejected('integer_overflow')
        return value
    if typ=='double precision':
        if type(value) not in {int,float} or not math.isfinite(value):raise MigrationRejected('invalid_float')
        return float(value)
    if typ=='timestamptz':
        # Only explicitly reviewed legacy optional fields accept blank as absent.
        if value=='' and field in {'assistant_memories.valid_from','assistant_memories.expires_at'}:
            return None
        try:
            result=datetime.fromisoformat(value[:-1]+'+00:00' if isinstance(value,str) and value.endswith('Z') else value)
            if result.tzinfo is None or result.utcoffset() is None:raise ValueError()
            return result.astimezone(timezone.utc)
        except (ValueError,TypeError):raise MigrationRejected('unknown_timestamp_timezone_or_format') from None
    if typ=='date':
        try:return date.fromisoformat(value)
        except (ValueError,TypeError):raise MigrationRejected('invalid_business_date') from None
    if typ=='text':
        if type(value) is not str:raise MigrationRejected('invalid_text')
        return value
    raise MigrationRejected('unsupported_source_column_type')


def _typed(typ,value):
    if value is None:return ['sql-null']
    if typ.startswith('shiliu.vector'):
        return [typ,[float(x).hex() for x in value.to_list()]]
    if typ=='jsonb':
        if not isinstance(value,JsonDocument):raise MigrationRejected('json_marker_missing')
        return ['jsonb',value.value]
    if typ=='timestamptz':return [typ,value.astimezone(timezone.utc).isoformat(timespec='microseconds')]
    if typ=='date':return [typ,value.isoformat()]
    if typ=='double precision':return [typ,value.hex()]
    if typ in {'bigint','integer'}:return [typ,str(value)]
    return [typ,value]


def logical_hash(rows,columns):
    # Types and explicit NULL tags are part of identity. Object keys sort,
    # arrays never sort; SQL NULL differs from JSON null even though both load
    # as Python None without a query IS NULL flag.
    digest=hashlib.sha256()
    digest.update(b'[')
    for index,row in enumerate(rows):
        if index:digest.update(b',')
        encoded=[[key,_typed(columns[key]['type'],row[key])] for key in sorted(row)]
        digest.update(json.dumps(encoded,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode())
    digest.update(b']')
    return digest.hexdigest()

"""Read-only PG catalog evidence and exact structural comparison to W02 mapping."""
from __future__ import annotations

import re
from typing import Any

from psycopg import Connection
from psycopg.rows import dict_row


def read_catalog(conn: Connection) -> dict[str, Any]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""SELECT c.relname AS table_name,a.attname AS name,
            format_type(a.atttypid,a.atttypmod) AS type,NOT a.attnotnull AS nullable,
            a.attidentity AS identity,pg_get_expr(d.adbin,d.adrelid) AS default
            FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace
            LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum
            WHERE n.nspname='shiliu' AND c.relkind='r' AND a.attnum>0 AND NOT a.attisdropped
            ORDER BY c.relname,a.attnum"""
        )
        tables: dict[str, Any] = {}
        for row in cur.fetchall():
            name=row.pop('table_name')
            tables.setdefault(name,dict(columns={},constraints=[],indexes=[],triggers=[]))['columns'][row['name']]=row
        cur.execute("""SELECT c.relname AS table_name,k.conname AS name,k.contype AS kind,
            k.convalidated AS validated,pg_get_constraintdef(k.oid) AS definition,
            ARRAY(SELECT a.attname FROM unnest(k.conkey) WITH ORDINALITY u(id,n)
                  JOIN pg_attribute a ON a.attrelid=k.conrelid AND a.attnum=u.id ORDER BY u.n) AS columns,
            p.relname AS parent,
            ARRAY(SELECT a.attname FROM unnest(k.confkey) WITH ORDINALITY u(id,n)
                  JOIN pg_attribute a ON a.attrelid=k.confrelid AND a.attnum=u.id ORDER BY u.n) AS references,
            k.confdeltype AS delete_action FROM pg_constraint k
            JOIN pg_class c ON c.oid=k.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace
            LEFT JOIN pg_class p ON p.oid=k.confrelid WHERE n.nspname='shiliu' ORDER BY c.relname,k.conname"""
        )
        for row in cur.fetchall():
            tables[row.pop('table_name')]['constraints'].append(row)
        cur.execute("""SELECT c.relname AS table_name,ic.relname AS name,pg_get_indexdef(i.indexrelid) AS definition,
            i.indisunique AS unique,pg_get_expr(i.indpred,i.indrelid) AS predicate,
            ARRAY(SELECT a.attname FROM unnest(i.indkey) WITH ORDINALITY u(id,n)
                  JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum=u.id ORDER BY u.n) AS columns,
            ARRAY(SELECT (v & 1)=1 FROM unnest(i.indoption) v) AS descending
            FROM pg_index i JOIN pg_class c ON c.oid=i.indrelid JOIN pg_class ic ON ic.oid=i.indexrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='shiliu' ORDER BY c.relname,ic.relname""")
        for row in cur.fetchall():
            tables[row.pop('table_name')]['indexes'].append(row)
        cur.execute("""SELECT c.relname AS table_name,t.tgname AS name,pg_get_triggerdef(t.oid) AS definition,
            t.tgenabled AS enabled FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='shiliu' AND NOT t.tgisinternal
            ORDER BY c.relname,t.tgname"""
        )
        for row in cur.fetchall():
            tables[row.pop('table_name')]['triggers'].append(row)
    return tables


def _default(value: str | None) -> str | None:
    return re.sub(r'::(?:text|bigint|integer|double precision)\b', '', value) if value else value


def compare_catalog(catalog: dict[str, Any], mapping: dict[str, Any]) -> list[str]:
    errors=[]
    target=mapping['tables']
    if set(catalog)!=set(target)|{'alembic_version'}:
        errors.append('table_set')
    for name,t in target.items():
        actual=catalog.get(name)
        if not actual:
            errors.append(name+':missing');continue
        if set(actual['columns'])!=set(t['columns']):errors.append(name+':column_set')
        for key,c in t['columns'].items():
            a=actual['columns'].get(key,{})
            typ=c['type'].replace('timestamptz','timestamp with time zone').replace('shiliu.vector','shiliu.vector')
            if a.get('type')!=typ:errors.append(name+'.'+key+':type')
            if a.get('nullable')!=c['nullable']:errors.append(name+'.'+key+':nullable')
            if (a.get('identity')=='d')!=c['identity']:errors.append(name+'.'+key+':identity')
            if _default(a.get('default'))!=_default(c['default']):errors.append(name+'.'+key+':default')
        cons=actual['constraints']
        if [k['columns'] for k in cons if k['kind']=='p']!=[t['pk']]:errors.append(name+':pk')
        uniques={tuple(k['columns']) for k in cons if k['kind']=='u'}
        if uniques!={tuple(u) for u in t['unique'] if u!=t['pk']}:errors.append(name+':unique')
        # PG deparses IN lists to ANY arrays and inserts casts; retain its full
        # definitions as evidence. Count and source-condition test coverage are
        # checked separately, rather than pretending textual equality is semantic.
        if len([k for k in cons if k['kind']=='c'])!=len(t['checks']):errors.append(name+':check_count')
        fks={k['name']:k for k in cons if k['kind']=='f'}
        if set(fks)!={f['name'] for f in t['foreign_keys']}:errors.append(name+':fk_set')
        for f in t['foreign_keys']:
            a=fks.get(f['name'],{})
            if (a.get('columns'),a.get('parent'),a.get('references'),a.get('delete_action'),a.get('validated'))!=(
                f['columns'],f['table'],f['references'],{'CASCADE':'c','RESTRICT':'r','NO ACTION':'a','SET NULL':'n'}[f['on_delete']],True):
                errors.append(name+':fk:'+f['name'])
        indexes={x['name']:x for x in actual['indexes']}
        for ix in t['indexes']:
            a=indexes.get(ix['name'],{})
            normalize=lambda x: re.sub(r'[\s()]','',_default(x) or '').replace('<>','!=')
            if (a.get('columns'),a.get('descending'),a.get('unique'),normalize(a.get('predicate')))!=(
                    [k[0] for k in ix['keys']],[k[1] for k in ix['keys']],ix['unique'],normalize(ix['where'])):
                errors.append(name+':index:'+ix['name'])
            if ix.get('access_method') and ('USING '+ix['access_method']+' ') not in a.get('definition',''):
                errors.append(name+':access_method:'+ix['name'])
        if 'search_vector' in t['columns'] and not any('USING gin (search_vector)' in x['definition'] for x in indexes.values()):
            errors.append(name+':gin')
        triggers={x['name']:x for x in actual['triggers']}
        for tr in t.get('constraint_triggers', []):
            a=triggers.get(tr['name'],{})
            definition=a.get('definition','')
            if ('AFTER '+tr['event'] not in definition or a.get('enabled')!='O'
                    or tr['function'] not in definition
                    or ('DEFERRABLE INITIALLY IMMEDIATE' not in definition if tr['deferrable'] and not tr['initially_deferred'] else False)):
                errors.append(name+':constraint_trigger:'+tr['name'])
        for tr in t['triggers']:
            a=triggers.get(tr['name'],{})
            if 'BEFORE '+tr['event'] not in a.get('definition','') or a.get('enabled')!='O':
                errors.append(name+':trigger:'+tr['name'])
    return errors

from shiliu.config import LIBPQ_DISABLED_PASSFILE
import os
import json
from pathlib import Path

import psycopg
import pytest

from shiliu.config import load_postgres_config
from shiliu.migration.schema import HEAD_REVISION
from shiliu.storage.postgres import PgDatabase
from shiliu.storage.scope import personal_context
from schema_support import formal_target


def test_full_upgrade_smoke():
    with formal_target(load_postgres_config()) as (runtime,admin):
        with PgDatabase(runtime) as db:
            db.validate_startup(revision=HEAD_REVISION,context=personal_context())
        with psycopg.connect(admin.database_url,passfile=LIBPQ_DISABLED_PASSFILE) as c:
            expected=json.loads(Path('migrations/contracts/schema26_target.json').read_text())['tables']
            actual={r[0] for r in c.execute("SELECT tablename FROM pg_tables WHERE schemaname='shiliu'")}
            assert actual==set(expected)|{'alembic_version','assistant_notifications'}


@pytest.mark.parametrize('revisions',[('head',),('0001_scope_core','0002_agent_domains','0003_retrieval_artifacts','0004_backfill_scope','0005_dispatch_input_identity','0006_research_reuse_scope','0007_collection_profiles','0008_dispatch_release','0009_research_ancestor_attempts','0010_research_control_lineage','0011_research_candidate_boundary','0012_collection_chunk_bm25','0013_assistant_notifications','0014_assistant_source_patch')])
def test_catalog_matches_expanded_contract_and_stepwise_upgrade(revisions):
    from shiliu.migration.catalog import read_catalog,compare_catalog
    with formal_target(load_postgres_config(),revisions=revisions) as (runtime,admin):
        with psycopg.connect(admin.database_url,passfile=LIBPQ_DISABLED_PASSFILE) as c:
            catalog=read_catalog(c)
            mapping=json.loads(Path('migrations/contracts/schema26_target.json').read_text())
            # Frozen ETL source contract predates the additive P1 index.
            from copy import deepcopy
            original=deepcopy({k:v for k,v in catalog.items() if k!='assistant_notifications'})
            # Assert the additive P2 contract before comparing the unchanged
            # frozen ETL mapping. Never rewrite the 0001-0012 baseline.
            proposal=original['assistant_wiki_proposals']
            added_columns={'content_version','supersedes_id','decided_at'}
            assert set(proposal['columns'])-set(mapping['tables']['assistant_wiki_proposals']['columns'])==added_columns
            added_constraints={'assistant_wiki_proposals_content_version_check','source_patch_null_source','proposal_owner_identity','proposal_supersedes_owner','proposal_not_self'}
            assert added_constraints.issubset({c['name'] for c in proposal['constraints']})
            proposal['columns']={k:v for k,v in proposal['columns'].items() if k not in added_columns}
            proposal['constraints']=[c for c in proposal['constraints'] if c['name'] not in added_constraints]
            assert compare_catalog(original,mapping)==[]
            out=Path('/tmp/shiliu-w01-20261023/catalog-'+HEAD_REVISION+'-'+str(len(revisions))+'.json')
            out.write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+'\n')


def test_source_mapping_covers_every_frozen_object_column_and_trigger():
    import hashlib
    mapping=json.loads(Path('migrations/contracts/schema26_target.json').read_text())
    source=Path('tests/fixtures/postgres_migration/schema26.json')
    assert hashlib.sha256(source.read_bytes()).hexdigest()==mapping['source_sha256']
    raw=json.loads(source.read_text())
    excluded={(o['database'],o['name'],o['type']) for o in mapping['excluded_source_objects']}
    for db,objects in raw['databases'].items():
        for obj in objects:
            if (db,obj['name'],obj['type']) in excluded:continue
            assert db=='main' and obj['tbl_name'] in mapping['tables']
            target=mapping['tables'][obj['tbl_name']]
            if obj['type']=='table':
                src={c['name'] for c in obj['columns']}
                dst={n for n,c in target['columns'].items() if 'source' in c}
                assert src-dst==({'backend_id'} if obj['name']=='assistant_memories' else set())
            if obj['type']=='trigger':
                assert any(tr['name']==obj['name'] and tr['source_sql']==obj['sql'] for tr in target['triggers'])


def test_all_source_immutable_and_lineage_triggers_on_real_tables():
    from psycopg import sql
    from seed_rows import SyntheticGraph,MAPPING
    with formal_target(load_postgres_config()) as (_,admin):
        with psycopg.connect(admin.database_url,passfile=LIBPQ_DISABLED_PASSFILE) as c:
            graph=SyntheticGraph(c)
            for name,t in MAPPING['tables'].items():
                if not t['triggers']:continue
                row=graph.ensure(name)
                where=sql.SQL(' AND ').join(sql.SQL('{}=%s').format(sql.Identifier(k)) for k in t['pk'])
                params=[row[k] for k in t['pk']]
                for trigger in t['triggers']:
                    # Conditional candidate-delta events get their required type.
                    # A WHEN with changed lineage must reject the exact field,
                    # whereas unconditional update also rejects a no-op.
                    field=t['pk'][0]
                    value=row[field]
                    if trigger['when'] and 'IS DISTINCT FROM' in trigger['when']:
                        import re
                        field=re.search(r'NEW\.(\w+)',trigger['when'])[1]
                        value=row[field]
                        value=(value+1) if isinstance(value,int) else str(value)+'_changed'
                    statement=sql.SQL('DELETE FROM shiliu.{} WHERE {}').format(sql.Identifier(name),where) if trigger['event']=='DELETE' else sql.SQL('UPDATE shiliu.{} SET {}=%s WHERE {}').format(sql.Identifier(name),sql.Identifier(field),where)
                    values=params if trigger['event']=='DELETE' else [value,*params]
                    with pytest.raises(psycopg.errors.CheckViolation,match='immutable_record'):
                        with c.transaction():
                            c.execute(statement,values)
                # Lineage-only triggers must continue to allow status/state updates.
                if any(tr['when'] and 'IS DISTINCT FROM' in tr['when'] for tr in t['triggers']):
                    if name=='model_dispatch_receipts':
                        c.execute(sql.SQL("UPDATE shiliu.{} SET status='released' WHERE {}").format(sql.Identifier(name),where),params)
                        continue
                    mutable='state_version' if 'state_version' in row else 'attempt_count' if 'attempt_count' in row else 'current_version'
                    c.execute(sql.SQL('UPDATE shiliu.{} SET {}={}+1 WHERE {}').format(sql.Identifier(name),sql.Identifier(mutable),sql.Identifier(mutable),where),params)


def test_cross_workspace_owner_thread_video_space_and_task_fk_negatives():
    from seed_rows import SyntheticGraph,insert,WORKSPACE
    from psycopg import sql
    with formal_target(load_postgres_config()) as (_,admin):
        with psycopg.connect(admin.database_url,passfile=LIBPQ_DISABLED_PASSFILE) as c:
            graph=SyntheticGraph(c)
            insert(c,'users',{'id':'other','display_name':'Synthetic other'})
            insert(c,'workspaces',{'id':'personal:other','kind':'personal','owner_user_id':'other'})
            video=graph.ensure('videos')
            outsider=dict(video,id=2,workspace_id='personal:other')
            insert(c,'videos',outsider)
            membership=graph.ensure('video_source_memberships')
            root=graph.ensure('assistant_threads')
            for table,row in [
                ('video_source_memberships',dict(membership,bvid='cross',video_id=2,membership_seq=2)),
                ('assistant_threads',dict(root,id='wrong-owner',principal_id='other')),
                ('assistant_memories',dict(graph.ensure('assistant_memories'),id='cross-space',scope_kind='space',scope_id='999',scope_space_id=999)),
            ]:
                with pytest.raises(psycopg.errors.ForeignKeyViolation):
                    with c.transaction():insert(c,table,row)
            run=graph.ensure('assistant_runs')
            insert(c,'assistant_threads',dict(root,id='other-thread'))
            msg=graph.ensure('assistant_messages')
            with pytest.raises(psycopg.errors.ForeignKeyViolation):
                with c.transaction():insert(c,'assistant_messages',dict(msg,id='cross-thread-msg',thread_id='other-thread',run_id=run['id'],seq=2))
            task=graph.ensure('research_tasks')
            insert(c,'research_tasks',dict(task,task_id='other-task'))
            goal=graph.ensure('research_goals')
            attempt=graph.ensure('research_attempts')
            with pytest.raises(psycopg.errors.ForeignKeyViolation):
                with c.transaction():insert(c,'research_attempts',dict(attempt,attempt_id='cross-task-attempt',task_id='other-task',ordinal=2))
            # Nullable uniqueness keeps multiple NULL chunk IDs (video units).
            unit=graph.ensure('retrieval_units')
            insert(c,'retrieval_units',dict(unit,unit_id='nullable-unique-second'))
            # Historical null video membership still anchored by its source.
            insert(c,'video_source_memberships',dict(membership,bvid='null-video',video_id=None,membership_seq=3))
            # Memory scope_id must be canonical text for a real same-owner Space.
            memory=graph.rows['assistant_memories']
            space=graph.ensure('assistant_spaces')
            with pytest.raises(psycopg.errors.CheckViolation):
                with c.transaction():insert(c,'assistant_memories',dict(memory,id='bad-scope-text',scope_kind='space',scope_space_id=space['id'],scope_id='01'))


def test_runtime_permissions_formal_revision_and_downgrade_refusal():
    from alembic import command
    from alembic.config import Config
    from shiliu.migration.schema import MIGRATIONS
    from shiliu.storage.errors import StorageError
    with formal_target(load_postgres_config()) as (runtime,admin):
        with PgDatabase(runtime) as db:
            db.validate_startup(revision=HEAD_REVISION,context=personal_context())
            for text in ('CREATE TABLE shiliu.forbidden (id int)',
                         'SELECT * FROM shiliu_migration.forbidden',
                         'SELECT * FROM shiliu.migration_runs',
                         "SET session_replication_role='replica'",
                         'ALTER TABLE shiliu.research_events DISABLE TRIGGER ALL'):
                with pytest.raises(StorageError) as caught:
                    with db.transaction() as c:c.execute(text)
                assert caught.value.sqlstate=='42501'
        # Call the actual revision downgrade, rather than simulating a DROP.
        import importlib.util
        path=MIGRATIONS/'versions'/'0003_retrieval_artifacts.py'
        spec=importlib.util.spec_from_file_location('test_revision',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with pytest.raises(RuntimeError,match='restore a verified'):
            module.downgrade()


def test_fixed_ddl_bytes_match_reviewed_mapping():
    import hashlib
    m=json.loads(Path('migrations/contracts/schema26_target.json').read_text())
    for name,digest in m['sql_sha256'].items():
        assert hashlib.sha256((Path('migrations/sql')/name).read_bytes()).hexdigest()==digest


def test_check_expressions_match_pg_parse_and_cross_evidence_roots():
    from psycopg import sql
    from seed_rows import SyntheticGraph,insert,MAPPING
    from shiliu.migration.catalog import read_catalog
    with formal_target(load_postgres_config()) as (_,admin):
        with psycopg.connect(admin.database_url,passfile=LIBPQ_DISABLED_PASSFILE) as c:
            catalog=read_catalog(c)
            for name,t in MAPPING['tables'].items():
                if not t['checks']:continue
                # Parse the independent mapping expressions through PG itself;
                # compare deparsed ASTs with static revision DDL, not CHECK counts.
                definitions=[sql.SQL('{} {}').format(sql.Identifier(k),sql.SQL(v['type'])) for k,v in t['columns'].items()]
                definitions += [sql.SQL('CHECK ({})').format(sql.SQL(x)) for x in t['checks']]
                c.execute(sql.SQL('CREATE TEMP TABLE expected_check ({})').format(sql.SQL(',').join(definitions)))
                expected=sorted(r[0] for r in c.execute("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid='pg_temp.expected_check'::regclass AND contype='c'"))
                assert expected==sorted(r['definition'] for r in catalog[name]['constraints'] if r['kind']=='c'),name
                c.execute('DROP TABLE expected_check')
            graph=SyntheticGraph(c)
            provenance=graph.ensure('research_evidence_provenance')
            action=graph.rows['research_inner_actions']
            goal=graph.rows['research_goals']
            attempt=graph.rows['research_attempts']
            insert(c,'research_goals',dict(goal,goal_id='goal-other',revision=2))
            insert(c,'research_attempts',dict(attempt,attempt_id='attempt-other',goal_id='goal-other',ordinal=2,status='terminal'))
            insert(c,'research_inner_actions',dict(action,action_id='action-other',goal_id='goal-other',attempt_id='attempt-other',action_key='other'))
            with pytest.raises(psycopg.errors.ForeignKeyViolation):
                with c.transaction():
                    insert(c,'research_evidence_provenance',dict(provenance,provenance_id='provenance-other',provenance_hash='other-hash',goal_id='goal-other',attempt_id='attempt-other',action_id='action-other'))


def test_cross_task_reused_material_allowed_only_within_workspace_and_real_parent():
    from seed_rows import SyntheticGraph,insert
    with formal_target(load_postgres_config()) as (_,admin):
        with psycopg.connect(admin.database_url,passfile=LIBPQ_DISABLED_PASSFILE) as c:
            first=SyntheticGraph(c)
            artifact_link=first.ensure('research_artifact_fact_links')
            page_link=first.ensure('research_topic_page_fact_links')
            route=first.ensure('research_artifact_routes')
            second=SyntheticGraph(c,suffix='_reused',numeric_id=2)
            fact=second.ensure('research_fact_revisions')
            child=second.rows['research_tasks']
            c.execute('UPDATE shiliu.research_tasks SET parent_task_id=%s WHERE task_id=%s',(first.rows['research_tasks']['task_id'],child['task_id']))
            # Incremental Artifact and its topic page keep their own task, while
            # referencing a fact from the independently researched child Task.
            insert(c,'research_artifact_fact_links',dict(artifact_link,link_id='cross-task-artifact-fact',fact_revision_id=fact['fact_revision_id'],ordinal=2))
            insert(c,'research_topic_page_fact_links',dict(page_link,link_id='cross-task-page-fact',fact_revision_id=fact['fact_revision_id'],ordinal=2))
            foreign_artifact=second.ensure('research_knowledge_artifact_revisions')
            insert(c,'research_artifact_routes',dict(route,record_id='cross-task-route',route_id='cross-task-route',command_id='cross-task-route-command',outcome_artifact_revision_id=foreign_artifact['artifact_revision_id'],continuation_task_id=child['task_id']))
            # Same-workspace but unrelated continuation is still an invalid root.
            third=SyntheticGraph(c,suffix='_unrelated',numeric_id=3)
            unrelated=third.ensure('research_tasks')
            with pytest.raises(psycopg.errors.ForeignKeyViolation):
                with c.transaction():insert(c,'research_artifact_routes',dict(route,record_id='unrelated-route',route_id='unrelated-route',command_id='unrelated-route-command',continuation_task_id=unrelated['task_id']))
            insert(c,'users',{'id':'foreign-owner','display_name':'Synthetic foreign'})
            insert(c,'workspaces',{'id':'personal:foreign-owner','kind':'personal','owner_user_id':'foreign-owner'})
            foreign=SyntheticGraph(c,workspace='personal:foreign-owner',user='foreign-owner',suffix='_foreign',numeric_id=4)
            outside=foreign.ensure('research_fact_revisions')
            for table,row in [('research_artifact_fact_links',dict(artifact_link,link_id='forbidden-cross-workspace-fact',fact_revision_id=outside['fact_revision_id'],ordinal=3)),('research_topic_page_fact_links',dict(page_link,link_id='forbidden-cross-workspace-page',fact_revision_id=outside['fact_revision_id'],ordinal=3))]:
                with pytest.raises(psycopg.errors.ForeignKeyViolation):
                    with c.transaction():insert(c,table,row)

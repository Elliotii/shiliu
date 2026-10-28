-- Thin business-result index. Bodies and business state remain in domain tables.
CREATE TABLE shiliu.assistant_notifications (
 id text PRIMARY KEY,
 workspace_id text NOT NULL,
 principal_id text NOT NULL,
 space_id bigint,
 event_key text NOT NULL,
 origin_type text NOT NULL CHECK (origin_type IN ('wiki_change','memory_change','plan_revision','wiki_proposal','job_issue','run_issue')),
 origin_id text NOT NULL,
 origin_version text,
 source_type text NOT NULL CHECK (source_type IN ('dialogue','auto_memory','video','manual','system')),
 cause_refs jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(cause_refs)='object'),
 effect_refs jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(effect_refs)='array'),
 undo_ref text,
 created_at timestamptz NOT NULL,
 activity_at timestamptz NOT NULL,
 read_at timestamptz,
 UNIQUE(workspace_id,principal_id,event_key),
 FOREIGN KEY(workspace_id,principal_id) REFERENCES shiliu.workspaces(id,owner_user_id),
 FOREIGN KEY(principal_id) REFERENCES shiliu.users(id),
 FOREIGN KEY(workspace_id,principal_id,space_id) REFERENCES shiliu.assistant_spaces(workspace_id,principal_id,id)
);
CREATE INDEX assistant_notifications_activity ON shiliu.assistant_notifications(workspace_id,principal_id,activity_at DESC,id DESC);
CREATE INDEX assistant_notifications_unread ON shiliu.assistant_notifications(workspace_id,principal_id,activity_at DESC,id DESC) WHERE read_at IS NULL;
INSERT INTO shiliu.assistant_runtime_state(workspace_id,principal_id,key,value,updated_at)
 SELECT id,owner_user_id,'messages_activation_at',clock_timestamp()::text,clock_timestamp() FROM shiliu.workspaces
 ON CONFLICT DO NOTHING;
-- Carry forward only the existing DML grantees; no global grants or owner changes.
DO $$ DECLARE r record; BEGIN
 FOR r IN SELECT DISTINCT grantee FROM information_schema.role_table_grants
 WHERE table_schema='shiliu' AND table_name='assistant_runtime_state'
 AND privilege_type='INSERT' AND grantee <> current_user AND grantee <> 'PUBLIC'
 LOOP EXECUTE format('GRANT SELECT,INSERT,UPDATE,DELETE ON shiliu.assistant_notifications TO %I',r.grantee); END LOOP;
END $$;

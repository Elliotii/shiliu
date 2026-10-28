SET search_path TO shiliu, public;
ALTER TABLE assistant_wiki_proposals
 ADD COLUMN content_version bigint NOT NULL DEFAULT 1 CHECK (content_version > 0),
 ADD COLUMN supersedes_id text,
 ADD COLUMN decided_at timestamptz,
 ADD CONSTRAINT source_patch_null_source CHECK (kind <> 'source_patch' OR (source_page_id IS NULL AND source_version IS NULL)),
 ADD CONSTRAINT proposal_owner_identity UNIQUE(workspace_id, principal_id, id),
 ADD CONSTRAINT proposal_supersedes_owner FOREIGN KEY(workspace_id, principal_id, supersedes_id)
   REFERENCES assistant_wiki_proposals(workspace_id, principal_id, id),
 ADD CONSTRAINT proposal_not_self CHECK (supersedes_id IS NULL OR supersedes_id <> id);
CREATE INDEX assistant_source_patch_pending ON assistant_wiki_proposals(workspace_id,principal_id,target_page_id)
 WHERE kind='source_patch' AND status='pending';

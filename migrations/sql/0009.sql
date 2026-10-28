-- Preserve the source kernel's read-only ancestor checkpoint branch/replay.
ALTER TABLE shiliu.research_attempts ADD CONSTRAINT scoped_research_attempt_id_key UNIQUE(workspace_id,attempt_id);
ALTER TABLE shiliu.research_checkpoints ADD CONSTRAINT scoped_research_checkpoint_id_key UNIQUE(workspace_id,checkpoint_id);
ALTER TABLE shiliu.research_attempts DROP CONSTRAINT fk_bf894ba839d15e052d10;
ALTER TABLE shiliu.research_attempts DROP CONSTRAINT fk_2f08791f6e3ded95311e;
ALTER TABLE shiliu.research_attempts ADD CONSTRAINT fk_ancestor_source_checkpoint FOREIGN KEY(workspace_id,source_checkpoint_id)
  REFERENCES shiliu.research_checkpoints(workspace_id,checkpoint_id) ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;
ALTER TABLE shiliu.research_attempts ADD CONSTRAINT fk_ancestor_parent_attempt FOREIGN KEY(workspace_id,parent_attempt_id)
  REFERENCES shiliu.research_attempts(workspace_id,attempt_id) ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

CREATE FUNCTION shiliu.validate_research_attempt_source() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE parent_task text; source_task text; source_attempt text; ancestor_found boolean;
BEGIN
  IF NEW.parent_attempt_id IS NULL THEN
    IF NEW.source_checkpoint_id IS NOT NULL THEN
      RAISE EXCEPTION 'research_attempt_source_lineage' USING ERRCODE='23503';
    END IF;
    RETURN NEW;
  END IF;
  SELECT task_id INTO parent_task FROM shiliu.research_attempts
    WHERE workspace_id=NEW.workspace_id AND attempt_id=NEW.parent_attempt_id;
  IF NOT FOUND THEN RAISE EXCEPTION 'research_attempt_source_lineage' USING ERRCODE='23503'; END IF;
  IF NEW.source_checkpoint_id IS NOT NULL THEN
    SELECT task_id,attempt_id INTO source_task,source_attempt FROM shiliu.research_checkpoints
      WHERE workspace_id=NEW.workspace_id AND checkpoint_id=NEW.source_checkpoint_id;
    IF NOT FOUND OR source_task IS DISTINCT FROM parent_task OR source_attempt IS DISTINCT FROM NEW.parent_attempt_id THEN
      RAISE EXCEPTION 'research_attempt_source_lineage' USING ERRCODE='23503';
    END IF;
  END IF;
  IF parent_task=NEW.task_id THEN RETURN NEW; END IF;
  IF NEW.cause NOT IN ('branch','replay') OR NEW.source_checkpoint_id IS NULL THEN
    RAISE EXCEPTION 'research_attempt_source_lineage' USING ERRCODE='23503';
  END IF;
  WITH RECURSIVE ancestors AS (
    SELECT task_id,parent_task_id,owner_user_id,ARRAY[task_id] AS path FROM shiliu.research_tasks
      WHERE workspace_id=NEW.workspace_id AND task_id=NEW.task_id
    UNION ALL
    SELECT t.task_id,t.parent_task_id,t.owner_user_id,a.path||t.task_id FROM shiliu.research_tasks t
      JOIN ancestors a ON t.task_id=a.parent_task_id AND t.owner_user_id=a.owner_user_id
      WHERE t.workspace_id=NEW.workspace_id AND NOT t.task_id=ANY(a.path)
  ) SELECT EXISTS(SELECT 1 FROM ancestors WHERE task_id=parent_task) INTO ancestor_found;
  IF NOT ancestor_found THEN RAISE EXCEPTION 'research_attempt_source_lineage' USING ERRCODE='23503'; END IF;
  RETURN NEW;
END $$;

-- Deferral keeps explicit offline closure import possible without disabling
-- immutable triggers. Runtime statements validate immediately by default.
CREATE CONSTRAINT TRIGGER research_attempt_source_lineage
AFTER INSERT OR UPDATE ON shiliu.research_attempts DEFERRABLE INITIALLY IMMEDIATE
FOR EACH ROW WHEN (NEW.parent_attempt_id IS NOT NULL OR NEW.source_checkpoint_id IS NOT NULL)
EXECUTE FUNCTION shiliu.validate_research_attempt_source();

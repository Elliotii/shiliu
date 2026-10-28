-- Candidate checkpoint is the outer/candidate boundary. Its referenced
-- provisional artifact was produced at an earlier inner checkpoint of the same
-- Task/Goal/Attempt; preserve both immutable checkpoint identities.
ALTER TABLE shiliu.research_knowledge_candidates DROP CONSTRAINT fk_aa0241091326b4dd97d2;
ALTER TABLE shiliu.research_knowledge_candidates ADD CONSTRAINT fk_candidate_artifact_attempt
  FOREIGN KEY(workspace_id,task_id,goal_id,attempt_id,provisional_artifact_id)
  REFERENCES shiliu.research_provisional_artifacts(workspace_id,task_id,goal_id,attempt_id,artifact_id)
  ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

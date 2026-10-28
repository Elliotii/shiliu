"""Immutable, domain-specific document identity; query policy stays independent."""

from dataclasses import replace
from psycopg.types.json import Jsonb
from shiliu.retrieval.dense import provider_identity, profile_identity


class DocumentProfile:
    def __init__(self, provider, policy):
        identity = provider_identity(provider)
        self.identity = replace(
            identity,
            projection_version=policy,
            input_policy_version=policy,
            dense_index_version=policy,
        )
        self.profile_id, self.fields = profile_identity(self)

    def model_identity(self):
        return self.identity

    def register(self, conn):
        i = self.identity
        conn.execute(
            "INSERT INTO shiliu.embedding_profiles (profile_id,model_id,model_revision,dimension,dtype,normalized,provider_version,document_policy_version,tokenizer_revision,max_tokens,identity) "
            "VALUES (%s,%s,%s,512,'float32',true,%s,%s,%s,512,%s) ON CONFLICT(profile_id) DO NOTHING",
            (
                self.profile_id,
                i.model_id,
                i.model_revision,
                i.provider_version,
                i.projection_version,
                i.model_revision,
                Jsonb(self.fields),
            ),
        )
        if (
            conn.execute(
                "SELECT identity FROM shiliu.embedding_profiles WHERE profile_id=%s",
                (self.profile_id,),
            ).fetchone()["identity"]
            != self.fields
        ):
            raise ValueError("embedding_profile_conflict")
        return self.profile_id

-- Tables of pydantic_ai_harness.spend.PostgresSpendStore (prefix "spend"), created here so the
-- application role needs no DDL rights. Keep in step with the harness version: the store
-- skips its own CREATE when both tables exist.
CREATE TABLE spend_counters (
    key_sha256 text PRIMARY KEY,
    key        bytea NOT NULL,
    usd_nanos  bigint NOT NULL,
    tokens     bigint NOT NULL,
    requests   bigint NOT NULL,
    unpriced   bigint NOT NULL,
    expires_at timestamptz
);
CREATE INDEX spend_counters_expiry ON spend_counters (expires_at) WHERE expires_at IS NOT NULL;

CREATE TABLE spend_dedup (
    marker_sha256 text PRIMARY KEY,
    expires_at    timestamptz NOT NULL
);
CREATE INDEX spend_dedup_expiry ON spend_dedup (expires_at);

-- Strict per-family order of agent messages: created_at ties inside one transaction.
ALTER TABLE agent_messages ADD COLUMN seq bigint GENERATED ALWAYS AS IDENTITY;
CREATE INDEX agent_messages_family_seq_idx ON agent_messages (family_id, seq);

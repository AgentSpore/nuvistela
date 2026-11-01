-- One world per family (family_id is the key); regenerating replaces the row in place.
-- `world` is jsonb, not columns: it is a nested document (locations, heroes) that the app
-- validates as one pydantic `World` and always reads and writes whole, never by field.
-- While status is 'pending' the previous world (if any) stays readable.
CREATE TABLE worlds (
    family_id    uuid PRIMARY KEY REFERENCES families (id) ON DELETE CASCADE,
    status       text NOT NULL CHECK (status IN ('pending', 'ready', 'fallback')),
    genre        text NOT NULL CHECK (genre IN ('fairy_tale', 'space', 'pirates', 'custom')),
    custom_genre text CHECK (custom_genre IS NULL OR char_length(custom_genre) <= 60),
    world        jsonb,
    updated_at   timestamptz NOT NULL DEFAULT now()
);

-- Shared queue for world / image / chapter work. Workers claim with FOR UPDATE SKIP LOCKED;
-- a 'running' row whose lock is older than the worker's lease is claimable again.
CREATE TABLE jobs (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    kind        text NOT NULL CHECK (kind IN ('world', 'image', 'chapter')),
    family_id   uuid NOT NULL REFERENCES families (id) ON DELETE CASCADE,
    payload     jsonb NOT NULL DEFAULT '{}',
    status      text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'done', 'failed')),
    attempts    int NOT NULL DEFAULT 0,
    next_run_at timestamptz NOT NULL DEFAULT now(),
    locked_at   timestamptz,
    last_error  text,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX jobs_claim_idx ON jobs (next_run_at) WHERE status IN ('pending', 'running');
CREATE INDEX jobs_family_kind_idx ON jobs (family_id, kind, created_at);

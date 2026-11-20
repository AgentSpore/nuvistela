-- Pictures of a family's world, stored in Postgres: the database is the only persistent volume,
-- and deleting the family removes its pictures with it.
-- world_job_id is worlds.job_id at the time the picture was ordered. It has no foreign key:
-- worlds.job_id is not unique and fallback worlds carry an id that is not in `jobs`.
-- A picture belongs to the family's current world only while worlds.job_id still equals it.
CREATE TABLE world_images (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    family_id    uuid NOT NULL REFERENCES families (id) ON DELETE CASCADE,
    world_job_id uuid NOT NULL,
    kind         text NOT NULL CHECK (kind IN ('cover')),
    prompt       text NOT NULL,
    status       text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'ready', 'failed')),
    sha256       text,
    bytes        bytea,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (family_id, world_job_id, kind),
    -- Only a ready picture has content; no hash or bytes that nothing produced.
    CONSTRAINT world_images_ready_has_content CHECK (
        (status = 'ready' AND sha256 ~ '^[0-9a-f]{64}$' AND bytes IS NOT NULL)
        OR (status <> 'ready' AND sha256 IS NULL AND bytes IS NULL)
    )
);

-- 3D scenes of a family's world, stored in Postgres like world_images: the database is the only
-- persistent volume, and deleting the family removes its scenes with it.
-- world_job_id is worlds.job_id at the time the scene was ordered. It has no foreign key:
-- worlds.job_id is not unique and fallback worlds carry an id that is not in `jobs`.
CREATE TABLE world_scenes (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    family_id    uuid NOT NULL REFERENCES families (id) ON DELETE CASCADE,
    world_job_id uuid NOT NULL,
    status       text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'ready', 'failed')),
    sha256       text,
    spz          bytea,
    panorama     bytea,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (family_id, world_job_id),
    -- Only a ready scene has content; sha256 is the hash of the spz bytes.
    CONSTRAINT world_scenes_ready_has_content CHECK (
        (status = 'ready' AND sha256 ~ '^[0-9a-f]{64}$' AND spz IS NOT NULL AND panorama IS NOT NULL)
        OR (status <> 'ready' AND sha256 IS NULL AND spz IS NULL AND panorama IS NULL)
    )
);

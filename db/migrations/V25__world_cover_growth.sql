-- Visible world growth (G3): a world gets a new cover on every 2nd milestone; the earlier covers
-- stay as history. milestone_no is 0 for the cover ordered with the world (kind 'cover') and the
-- milestone's ordinal for a growth cover (kind 'cover_growth'), so the 3D scene, which is built
-- from the one 'cover' row, never meets a second one.
ALTER TABLE world_images DROP CONSTRAINT world_images_kind_check;
ALTER TABLE world_images
    ADD COLUMN milestone_no int NOT NULL DEFAULT 0 CHECK (milestone_no >= 0),
    ADD CONSTRAINT world_images_kind_check CHECK (kind IN ('cover', 'cover_growth')),
    ADD CONSTRAINT world_images_growth_has_milestone CHECK ((kind = 'cover') = (milestone_no = 0));
ALTER TABLE world_images DROP CONSTRAINT world_images_family_id_world_job_id_kind_key;
ALTER TABLE world_images
    ADD CONSTRAINT world_images_world_kind_milestone_key
    UNIQUE (family_id, world_job_id, kind, milestone_no);

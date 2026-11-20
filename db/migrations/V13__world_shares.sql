-- Public share links of a family's world cover. The row holds everything the public page shows:
-- title and genre are fixed at creation (title NULL when it carried a member's name; genre is a
-- key, 'custom' for a family's own text), so the world's text is never read again.
-- world_job_id and image_sha pin the world and cover of that moment: a regenerated world does not
-- change a link already sent. Only the SHA-256 of the token is stored.
CREATE TABLE world_shares (
    id           uuid PRIMARY KEY,
    family_id    uuid NOT NULL REFERENCES families (id) ON DELETE CASCADE,
    world_job_id uuid NOT NULL,
    image_sha    text NOT NULL CHECK (image_sha ~ '^[0-9a-f]{64}$'),
    token_sha256 text NOT NULL UNIQUE CHECK (token_sha256 ~ '^[0-9a-f]{64}$'),
    title        text,
    genre        text NOT NULL CHECK (genre IN ('fairy_tale', 'space', 'pirates', 'custom')),
    created_by   uuid REFERENCES members (id) ON DELETE SET NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    revoked_at   timestamptz
);
-- One active link per world version.
CREATE UNIQUE INDEX world_shares_one_active
    ON world_shares (family_id, world_job_id) WHERE revoked_at IS NULL;

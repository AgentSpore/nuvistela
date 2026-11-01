-- Emails are stored lower-cased by the service; the CHECK keeps the unique key honest.
CREATE TABLE waitlist (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email          text NOT NULL UNIQUE CHECK (email = lower(email) AND char_length(email) <= 254),
    family_size    smallint NOT NULL CHECK (family_size BETWEEN 1 AND 12),
    kids_age_bands text[] NOT NULL DEFAULT '{}'
        CHECK (kids_age_bands <@ ARRAY['3-5', '6-9', '10-13', '14-17']),
    locale         text NOT NULL DEFAULT 'ru' CHECK (locale IN ('ru', 'en')),
    created_at     timestamptz NOT NULL DEFAULT now()
);

-- Funnel events carry ids and coarse props only: never email, names or message text.
CREATE TABLE events (
    id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    family_id uuid REFERENCES families (id) ON DELETE SET NULL,
    member_id uuid REFERENCES members (id) ON DELETE SET NULL,
    kind      text NOT NULL,
    at        timestamptz NOT NULL DEFAULT now(),
    props     jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX events_kind_at_idx ON events (kind, at);
-- Once-per-member kinds: concurrent requests cannot write a second row.
CREATE UNIQUE INDEX events_member_once_idx ON events (member_id, kind)
    WHERE kind IN ('member_first_seen', 'return_d1', 'return_d7');

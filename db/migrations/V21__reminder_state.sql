-- "Quest waiting" bookkeeping per family and channel: one send per local day, and a count of
-- sends since the family was last in the game (a later last_adventure_poll_at resets it).
CREATE TABLE reminder_state (
    family_id  uuid NOT NULL REFERENCES families (id) ON DELETE CASCADE,
    channel    text NOT NULL CHECK (channel IN ('push', 'telegram')),
    last_sent_at timestamptz NOT NULL,
    unanswered int NOT NULL DEFAULT 0 CHECK (unanswered >= 0),
    PRIMARY KEY (family_id, channel)
);

ALTER TABLE jobs DROP CONSTRAINT jobs_kind_check,
    ADD CONSTRAINT jobs_kind_check CHECK (kind IN ('world', 'image', 'chapter', 'notify'));

-- "Opened" is reported by the service worker and may repeat: one event per member, kind and UTC day.
CREATE UNIQUE INDEX events_reminder_opened_daily_idx
    ON events (member_id, (props ->> 'kind'), ((at AT TIME ZONE 'UTC')::date))
    WHERE kind = 'reminder_opened';

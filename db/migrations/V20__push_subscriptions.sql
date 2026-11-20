-- Web Push devices of adult members. endpoint, p256dh and auth are personal device data: they are
-- never logged and never leave the database except to the push service itself.
CREATE TABLE push_subscriptions (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    member_id  uuid NOT NULL REFERENCES members (id) ON DELETE CASCADE,
    family_id  uuid NOT NULL REFERENCES families (id) ON DELETE CASCADE,
    endpoint   text NOT NULL UNIQUE CHECK (char_length(endpoint) <= 2048),
    p256dh     text NOT NULL CHECK (char_length(p256dh) <= 256),
    auth       text NOT NULL CHECK (char_length(auth) <= 64),
    tz         text NOT NULL CHECK (char_length(tz) <= 64),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX push_subscriptions_family_idx ON push_subscriptions (family_id);
CREATE INDEX push_subscriptions_member_idx ON push_subscriptions (member_id);

-- Last time any client polled the adventure screen (written at most every few seconds). It tells
-- an open game tab (no "chapter ready" push) and "was here today" (no "quest waiting" push).
ALTER TABLE families ADD COLUMN last_adventure_poll_at timestamptz;

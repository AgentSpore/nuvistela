CREATE TABLE families (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    title      text NOT NULL,
    locale     text NOT NULL DEFAULT 'ru' CHECK (locale IN ('ru', 'en')),
    created_at timestamptz NOT NULL DEFAULT now()
);

-- invite_token_hash is single-use: NULL once consumed. A login lives in sessions.
CREATE TABLE members (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    family_id         uuid NOT NULL REFERENCES families (id) ON DELETE CASCADE,
    display_name      text NOT NULL CHECK (char_length(display_name) BETWEEN 1 AND 40),
    age_band          text NOT NULL CHECK (age_band IN ('3-5', '6-9', '10-13', '14-17', 'adult')),
    role              text NOT NULL CHECK (role IN ('adult', 'child')),
    interests         text[] NOT NULL DEFAULT '{}' CHECK (cardinality(interests) <= 10),
    tg_user_id        bigint,
    invite_token_hash text UNIQUE,
    invite_expires_at timestamptz,
    created_at        timestamptz NOT NULL DEFAULT now(),
    UNIQUE (family_id, tg_user_id)
);

CREATE TABLE sessions (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    member_id  uuid NOT NULL REFERENCES members (id) ON DELETE CASCADE,
    token_hash text NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL
);
CREATE INDEX sessions_member_id_idx ON sessions (member_id);

CREATE TABLE tg_chats (
    chat_id   bigint PRIMARY KEY,
    family_id uuid NOT NULL REFERENCES families (id) ON DELETE CASCADE
);
CREATE INDEX tg_chats_family_id_idx ON tg_chats (family_id);

CREATE TABLE link_codes (
    code_hash  text PRIMARY KEY,
    member_id  uuid NOT NULL REFERENCES members (id) ON DELETE CASCADE,
    expires_at timestamptz NOT NULL
);
CREATE INDEX link_codes_member_id_idx ON link_codes (member_id);

CREATE TABLE agent_messages (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    family_id  uuid NOT NULL REFERENCES families (id) ON DELETE CASCADE,
    member_id  uuid REFERENCES members (id) ON DELETE SET NULL,
    role       text NOT NULL CHECK (role IN ('user', 'agent', 'system')),
    channel    text NOT NULL,
    content    jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX agent_messages_member_id_idx ON agent_messages (member_id);

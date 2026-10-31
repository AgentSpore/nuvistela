CREATE TABLE families (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    title      text NOT NULL,
    locale     text NOT NULL DEFAULT 'ru' CHECK (locale IN ('ru', 'en')),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE members (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    family_id         uuid NOT NULL REFERENCES families (id) ON DELETE CASCADE,
    display_name      text NOT NULL CHECK (char_length(display_name) BETWEEN 1 AND 40),
    age_band          text NOT NULL CHECK (age_band IN ('3-5', '6-9', '10-13', '14-17', 'adult')),
    role              text NOT NULL CHECK (role IN ('adult', 'child')),
    interests         text[] NOT NULL DEFAULT '{}' CHECK (cardinality(interests) <= 10),
    tg_user_id        bigint UNIQUE,
    invite_token_hash text NOT NULL UNIQUE,
    created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX members_family_id_idx ON members (family_id);

CREATE TABLE quests (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    family_id   uuid NOT NULL REFERENCES families (id) ON DELETE CASCADE,
    title       text NOT NULL,
    assignee_id uuid NOT NULL REFERENCES members (id),
    created_by  uuid NOT NULL REFERENCES members (id),
    status      text NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'claimed', 'confirmed', 'cancelled')),
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX quests_family_id_idx ON quests (family_id);
CREATE INDEX quests_assignee_id_idx ON quests (assignee_id);
CREATE INDEX quests_created_by_idx ON quests (created_by);

CREATE TABLE quest_events (
    id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    quest_id uuid NOT NULL REFERENCES quests (id) ON DELETE CASCADE,
    kind     text NOT NULL CHECK (kind IN ('claimed', 'confirmed', 'rejected')),
    actor_id uuid NOT NULL REFERENCES members (id),
    at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX quest_events_quest_id_idx ON quest_events (quest_id);
CREATE INDEX quest_events_actor_id_idx ON quest_events (actor_id);

CREATE TABLE chapters (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    family_id  uuid NOT NULL REFERENCES families (id) ON DELETE CASCADE,
    number     integer NOT NULL CHECK (number > 0),
    quest_id   uuid REFERENCES quests (id),
    kind       text NOT NULL CHECK (kind IN ('daily', 'weekly')),
    text       text NOT NULL DEFAULT '',
    model      text,
    status     text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'ready', 'fallback')),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (family_id, number)
);
CREATE INDEX chapters_quest_id_idx ON chapters (quest_id);

CREATE TABLE chapter_jobs (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    chapter_id  uuid NOT NULL REFERENCES chapters (id) ON DELETE CASCADE,
    attempts    integer NOT NULL DEFAULT 0,
    next_run_at timestamptz NOT NULL DEFAULT now(),
    locked_at   timestamptz
);
CREATE INDEX chapter_jobs_chapter_id_idx ON chapter_jobs (chapter_id);
CREATE INDEX chapter_jobs_next_run_at_idx ON chapter_jobs (next_run_at);

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

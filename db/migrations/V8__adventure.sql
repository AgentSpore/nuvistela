-- One adventure per family: quests the family does, a "done" mark per quest, and the chapter the
-- model writes after each mark. Integrity lives in these keys: concurrent or repeated requests
-- hit a UNIQUE conflict instead of writing a second row.

-- seq numbers a family's quests from 1. At most one quest per family is open at a time.
-- member_id is who the quest is for; the row survives that member's removal.
CREATE TABLE quests (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    family_id   uuid NOT NULL REFERENCES families (id) ON DELETE CASCADE,
    member_id   uuid REFERENCES members (id) ON DELETE SET NULL,
    seq         int NOT NULL CHECK (seq >= 1),
    title       text NOT NULL CHECK (char_length(title) BETWEEN 1 AND 80),
    description text NOT NULL CHECK (char_length(description) BETWEEN 1 AND 400),
    skill       text NOT NULL,
    source      text NOT NULL CHECK (source IN ('template', 'model')),
    status      text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'done')),
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (family_id, seq),
    UNIQUE (id, family_id)  -- target of the composite keys below: a child row cannot name another family
);
CREATE UNIQUE INDEX quests_one_open_idx ON quests (family_id) WHERE status = 'open';

-- UNIQUE (quest_id, kind): a quest is marked done once. idem_key is the client's retry key;
-- the note is the member's free text (data, never an instruction), capped at 280 characters.
CREATE TABLE quest_events (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    quest_id   uuid NOT NULL,
    family_id  uuid NOT NULL,
    member_id  uuid REFERENCES members (id) ON DELETE SET NULL,
    kind       text NOT NULL CHECK (kind IN ('done')),
    note       text CHECK (note IS NULL OR char_length(note) <= 280),
    idem_key   text CHECK (idem_key IS NULL OR char_length(idem_key) <= 128),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (quest_id, kind),
    FOREIGN KEY (quest_id, family_id) REFERENCES quests (id, family_id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX quest_events_idem_idx ON quest_events (family_id, idem_key)
    WHERE idem_key IS NOT NULL;

-- One chapter per quest. seq repeats the quest's seq, so the story reads in quest order.
-- job_id is the job allowed to write this row, as in worlds: a superseded job's result is dropped.
CREATE TABLE chapters (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    family_id   uuid NOT NULL,
    quest_id    uuid NOT NULL UNIQUE,
    seq         int NOT NULL CHECK (seq >= 1),
    status      text NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'writing', 'ready', 'delayed_model', 'delayed_budget')),
    title       text,
    body        text,
    summary     text,
    job_id      uuid,
    next_run_at timestamptz,
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (family_id, seq),
    UNIQUE (id, family_id),
    FOREIGN KEY (quest_id, family_id) REFERENCES quests (id, family_id) ON DELETE CASCADE
);

-- Money reserved before a paid model call and settled after it. UNIQUE (job_id, attempt):
-- a redelivered job attempt cannot reserve twice. Amounts are micro-USD (integers, no floats).
-- The rows outlive their family and chapter (both ids become NULL, no personal data in the row):
-- deleting a family must not shrink the money already counted against the daily cap.
CREATE TABLE llm_spend (
    id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    family_id          uuid REFERENCES families (id) ON DELETE SET NULL,
    chapter_id         uuid REFERENCES chapters (id) ON DELETE SET NULL
        DEFERRABLE INITIALLY DEFERRED,
    job_id             uuid NOT NULL,
    attempt            int NOT NULL CHECK (attempt >= 1),
    reserved_micro_usd bigint NOT NULL CHECK (reserved_micro_usd >= 0),
    actual_micro_usd   bigint CHECK (actual_micro_usd IS NULL OR actual_micro_usd >= 0),
    state              text NOT NULL DEFAULT 'reserved' CHECK (state IN ('reserved', 'settled')),
    created_at         timestamptz NOT NULL DEFAULT now(),
    UNIQUE (job_id, attempt),
    -- Keeps a chapter reference inside its own family. It is not checked once family_id is
    -- NULL, which is why chapter_id also has its own key above to clear it on a family delete
    -- (deferred: the family delete nulls family_id and drops the chapter in one statement).
    FOREIGN KEY (chapter_id, family_id) REFERENCES chapters (id, family_id)
        ON DELETE SET NULL (chapter_id)
);
CREATE INDEX llm_spend_created_at_idx ON llm_spend (created_at);

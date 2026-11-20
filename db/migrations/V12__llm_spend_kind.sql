-- Image calls are capped apart from text, so a reservation says which kind of call it is for.
ALTER TABLE llm_spend
    ADD COLUMN kind text NOT NULL DEFAULT 'text' CHECK (kind IN ('text', 'image'));

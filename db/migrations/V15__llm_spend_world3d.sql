-- 3D world generation is capped apart from text and pictures: one draft costs more than the
-- whole daily picture allowance, so it needs its own kind of spend.
ALTER TABLE llm_spend DROP CONSTRAINT llm_spend_kind_check;
ALTER TABLE llm_spend
    ADD CONSTRAINT llm_spend_kind_check CHECK (kind IN ('text', 'image', 'world3d'));

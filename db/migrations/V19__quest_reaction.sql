-- The world's instant answer to a finished quest, written by the model with the quest (R1).
-- NULL for template quests, fallback worlds and quests created before this migration.
ALTER TABLE quests
    ADD COLUMN reaction text CHECK (reaction IS NULL OR char_length(reaction) <= 280);

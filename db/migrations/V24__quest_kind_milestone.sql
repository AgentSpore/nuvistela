-- Visible world growth (G1): the task kind of each quest and the milestone line of a chapter.
-- NULL for quests and chapters created before this migration and for template quests.
ALTER TABLE quests
    ADD COLUMN kind text CHECK (kind IN ('say', 'make', 'move', 'care', 'find', 'gift'));
ALTER TABLE chapters
    ADD COLUMN milestone text CHECK (char_length(milestone) <= 80);

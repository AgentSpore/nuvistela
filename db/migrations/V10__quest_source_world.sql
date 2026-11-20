-- A quest written with the world (its first_quest) has its own source, next to the template
-- fallback and the chapter writer's model quests.
ALTER TABLE quests DROP CONSTRAINT quests_source_check;
ALTER TABLE quests ADD CONSTRAINT quests_source_check CHECK (source IN ('template', 'model', 'world'));

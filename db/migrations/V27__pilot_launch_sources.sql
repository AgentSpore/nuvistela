-- Launch posts link the landing with ?source=x|telegram|substack|youtube; the pilot report breaks
-- sessions and leads down by these first-touch sources.
ALTER TABLE pilot_sessions DROP CONSTRAINT pilot_sessions_source_check;
ALTER TABLE pilot_sessions ADD CONSTRAINT pilot_sessions_source_check CHECK (source IN (
    'direct', 'share', 'community', 'newsletter', 'x', 'telegram', 'substack', 'youtube'
));
ALTER TABLE pilot_events DROP CONSTRAINT pilot_events_source_check;
ALTER TABLE pilot_events ADD CONSTRAINT pilot_events_source_check CHECK (source IN (
    'direct', 'share', 'community', 'newsletter', 'x', 'telegram', 'substack', 'youtube'
));

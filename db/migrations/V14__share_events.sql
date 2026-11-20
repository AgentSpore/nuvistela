-- Share-card accounting reuses pilot_events. Link created/revoked are recorded by the server for a
-- family, not a browser session, so those rows have no session and no locale; the funnel counts
-- them by kind only (no token, share id or family id is stored).
ALTER TABLE pilot_events DROP CONSTRAINT IF EXISTS pilot_events_kind_check;
ALTER TABLE pilot_events ADD CONSTRAINT pilot_events_kind_check CHECK (kind IN (
    'landing_view', 'demo_start', 'demo_complete', 'cta_click', 'share_click', 'lead_created',
    'share_created', 'share_revoked', 'share_viewed', 'share_cta'
));
ALTER TABLE pilot_events ALTER COLUMN session_id DROP NOT NULL;
ALTER TABLE pilot_events ALTER COLUMN locale DROP NOT NULL;
-- Only the two server-side kinds may lack a session, and then locale is absent too.
ALTER TABLE pilot_events ADD CONSTRAINT pilot_events_server_kind_check CHECK (
    (session_id IS NULL) = (kind IN ('share_created', 'share_revoked'))
    AND (locale IS NULL) = (session_id IS NULL)
);

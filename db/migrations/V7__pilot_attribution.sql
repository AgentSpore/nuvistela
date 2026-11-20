CREATE TABLE IF NOT EXISTS pilot_sessions (
    session_id uuid PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    source text NOT NULL CHECK (source IN ('direct', 'share', 'community', 'newsletter')),
    locale text NOT NULL CHECK (locale IN ('ru', 'en', 'es', 'zh-CN')),
    internal boolean NOT NULL DEFAULT false
);
CREATE INDEX IF NOT EXISTS pilot_sessions_created_idx ON pilot_sessions (created_at);
CREATE TABLE IF NOT EXISTS pilot_events (
    event_id uuid PRIMARY KEY,
    session_id uuid NOT NULL REFERENCES pilot_sessions (session_id),
    at timestamptz NOT NULL DEFAULT clock_timestamp(),
    kind text NOT NULL CHECK (kind IN (
        'landing_view', 'demo_start', 'demo_complete', 'cta_click', 'share_click', 'lead_created'
    )),
    locale text NOT NULL CHECK (locale IN ('ru', 'en', 'es', 'zh-CN')),
    source text NOT NULL CHECK (source IN ('direct', 'share', 'community', 'newsletter')),
    intent text CHECK (intent IN ('solo', 'family'))
);
CREATE INDEX IF NOT EXISTS pilot_events_session_idx ON pilot_events (session_id);

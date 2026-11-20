-- requeue_due runs before every chapter claim and looks only at delayed chapters.
-- A partial index keeps that lookup off a full scan of chapters (EXPLAIN at 50k rows: cost 1546 -> 8).
CREATE INDEX chapters_requeue_idx ON chapters (next_run_at)
    WHERE status IN ('delayed_model', 'delayed_budget');

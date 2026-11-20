ALTER TABLE waitlist
    DROP CONSTRAINT IF EXISTS waitlist_locale_check,
    ADD CONSTRAINT waitlist_locale_check CHECK (locale IN ('ru', 'en', 'es', 'zh-CN'));

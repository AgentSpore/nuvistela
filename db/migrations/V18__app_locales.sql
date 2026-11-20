-- The app is served in four locales, like the landing tables (V6, V7).
ALTER TABLE families
    DROP CONSTRAINT IF EXISTS families_locale_check,
    ADD CONSTRAINT families_locale_check CHECK (locale IN ('ru', 'en', 'es', 'zh-CN'));

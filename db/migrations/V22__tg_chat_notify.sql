-- Consent to soft reminders in a linked Telegram chat; off until someone sends /notify on.
ALTER TABLE tg_chats ADD COLUMN notify boolean NOT NULL DEFAULT false;

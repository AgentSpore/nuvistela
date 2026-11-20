-- An own-world description grows from a genre label (60) to a short world brief (300).
ALTER TABLE worlds DROP CONSTRAINT worlds_custom_genre_check;
ALTER TABLE worlds
    ADD CONSTRAINT worlds_custom_genre_check
    CHECK (custom_genre IS NULL OR char_length(custom_genre) <= 300);

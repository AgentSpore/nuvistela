from app.domain.world import scrub


def test_scrub_removes_cyrillic_declensions_of_a_name() -> None:
    assert scrub("Подарок для Миши и Мише", ["Миша"]) == "Подарок для и"


def test_scrub_keeps_words_that_only_share_letters_with_a_short_name() -> None:
    assert scrub("кот, который любит котов", ["Кот"]) == "который любит котов"


def test_scrub_stem_match_does_not_mangle_unrelated_long_words() -> None:
    assert scrub("который котиков", ["Котик"]) == "который"


def test_scrub_removes_phrase_words_ages_and_digits() -> None:
    assert (
        scrub("Anya, aged 6-9, loves board games 12", ["Anya", "6-9", "board games"])
        == "aged, loves"
    )

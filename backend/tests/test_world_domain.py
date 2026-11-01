import pytest

from app.domain.world import scrub


def test_scrub_removes_cyrillic_declensions_of_a_name() -> None:
    assert scrub("Подарок для Миши и Мише", ["Миша"]) == "Подарок для и"


def test_scrub_keeps_which_but_drops_cat_forms_for_a_short_name() -> None:
    assert scrub("кот, который любит котов", ["Кот"]) == "который любит"


def test_scrub_stem_match_does_not_mangle_unrelated_long_words() -> None:
    assert scrub("который котиков", ["Котик"]) == "который"


def test_scrub_removes_phrase_words_ages_and_digits() -> None:
    assert (
        scrub("Anya, aged 6-9, loves board games 12", ["Anya", "6-9", "board games"])
        == "aged, loves"
    )


def test_scrub_removes_declensions_of_a_three_letter_name() -> None:
    assert scrub("Котов, коту", ["кот"]) == ""
    assert scrub("Ани, Аню", ["Аня"]) == ""


def test_scrub_keeps_unrelated_words_with_the_same_first_letters() -> None:
    assert scrub("Остров, который любит", ["кот"]) == "Остров, который любит"
    assert scrub("Остров, который любит", ["коты"]) == "Остров, который любит"


@pytest.mark.parametrize(
    ("name", "word"),
    [
        ("Ира", "ирис"),
        ("Ира", "ирга"),
        ("море", "мороз"),
        ("море", "морж"),
        ("Ника", "никто"),
        ("Ника", "никак"),
        ("Ден", "день"),
        ("Ян", "янка"),
        ("Leo", "leaf"),
        ("Leo", "left"),
        ("Mia", "mint"),
        ("Mia", "mild"),
        ("Mia", "mist"),
        ("Eva", "even"),
        ("Eva", "ever"),
        ("Ия", "и"),
    ],
)
def test_scrub_keeps_ordinary_words_that_share_a_stem(name: str, word: str) -> None:
    assert scrub(f"{word} тут", [name]) == f"{word} тут"


@pytest.mark.parametrize(
    ("name", "forms"),
    [
        ("Ден", "Ден Дена Дену"),
        ("Ия", "Ия Ии Ию"),
        ("Лев", "Леву"),
        ("Ира", "Иры Иру Ирой"),
        ("Mia", "Mia mia"),
    ],
)
def test_scrub_removes_real_case_forms(name: str, forms: str) -> None:
    assert scrub(forms, [name]) == ""

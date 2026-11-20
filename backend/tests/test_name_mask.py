"""mask_names: a child's real name must not reach the model through the note."""

import unicodedata

import pytest

from app.agent.name_mask import mask_names

CASES = [
    (
        "Миша рассказал папе, и Мише дали ключ. Мишей гордятся.",
        ["Миша"],
        "(player) рассказал папе, и (player) дали ключ. (player) гордятся.",
    ),
    ("Ольга пришла, мы позвали Ольгу.", ["Ольга"], "(player) пришла, мы позвали (player)."),
    ("Lucía's dog; Lucía ran. LUCÍA!", ["Lucía"], "(player)'s dog; (player) ran. (player)!"),
    ("小明把灯点亮了", ["小明"], "(player)把灯点亮了"),
    ("Ли и Лиса: Ли ушёл", ["Ли"], "(player) и Лиса: (player) ушёл"),
    ("Мирон и Мила", ["Миша"], "Мирон и Мила"),
    ("a (b) c.* d", ["(b)", "c.*"], "a (player) (player) d"),
    ("Anya Smith met Smith", ["Anya Smith"], "(player) (player) met (player)"),
    ("nothing here", ["", " "], "nothing here"),
    ("Миша", [], "Миша"),
    (
        "Иван и Ивану, с Иваном, Ивана, Иване",
        ["Иван"],
        "(player) и (player), с (player), (player), (player)",
    ),
    ("Сергей, Сергея", ["Сергей"], "(player), (player)"),
    ("Надю, Наде, Надей, Нади", ["Надя"], "(player), (player), (player), (player)"),
    ("Ivan's idea, Ivan", ["Ivan"], "(player)'s idea, (player)"),
    ("Ivana ran", ["Ivan"], "Ivana ran"),
    # round 2: leaks found on realistic notes
    (
        "Мы с Аней пошли, Ане понравилось, Аню хвалили",
        ["Аня"],
        "Мы с (player) пошли, (player) понравилось, (player) хвалили",
    ),
    ("Оле и Олю, Иру, Юле", ["Оля", "Ира", "Юля"], "(player) и (player), (player), (player)"),
    (
        "Пришли с Сергеем, Андреем и Матвеем",
        ["Сергей", "Андрей", "Матвей"],
        "Пришли с (player), (player) и (player)",
    ),
    ("с Игорем и Игорю", ["Игорь"], "с (player) и (player)"),
    ("с Ильёй, Илье, Ильи, Ильюша", ["Илья"], "с (player), (player), (player), (player)"),
    ("Артем сам собрал, Артёму", ["Артём"], "(player) сам собрал, (player)"),
    ("Артём сам, Артему", ["Артем"], "(player) сам, (player)"),
    ("Женя и его жена, жену", ["Женя"], "(player) и его жена, жену"),
    ("ты мне дашь? Даша да", ["Даша"], "ты мне дашь? (player) да"),
    ("я верю в Веру", ["Вера"], "я верю в (player)"),
    (
        "Сашенька и Сашеньке, Мишка молодцы",
        ["Саша", "Миша"],
        "(player) и (player), (player) молодцы",
    ),
    ("Maria and Jose built it", ["María José"], "(player) and (player) built it"),
    ("Ana and Lucía", ["Ana-Lucía"], "(player) and (player)"),
    ("Анна и Мария", ["Анна-Мария"], "(player) и (player)"),
    ("小明把灯点亮了", ["王小明"], "(player)把灯点亮了"),
    (
        "Никита, Никиту, Никитой, Сашей, Саше",
        ["Никита", "Саша"],
        "(player), (player), (player), (player), (player)",
    ),
    (
        "Bobbys idea, Bobby's idea, Marias bag",
        ["Bobby", "Maria"],
        "(player) idea, (player)'s idea, (player) bag",
    ),
    ("花子が来た", ["山田花子"], "(player)が来た"),
    ("いくらでも、くらい", ["さくら"], "いくらでも、くらい"),
    ("левой рукой, налево, леве, Леву, Льва", ["Лев"], "левой рукой, налево, леве, (player), Льва"),
    ("we will go, Will said", ["Will"], "we (player) go, (player) said"),
]


@pytest.mark.parametrize(("text", "names", "want"), CASES)
def test_mask_names(text: str, names: list[str], want: str) -> None:
    assert mask_names(text, names) == want


# Ordinary words that merely share a stem with a name must stay intact.
COLLATERAL = {
    "Надя": ["Надо", "надолго"],
    "Вера": ["верно", "верный", "верить"],
    "Мила": ["милый", "милая"],
    "Миша": ["мишень", "мишура"],
    "Иван": ["Иванов", "Иванна"],
    "Женя": ["жена", "жену"],
    "Даша": ["дашь"],
    "Аня": ["аннотация", "анекдот"],
}


@pytest.mark.parametrize(("name", "words"), COLLATERAL.items())
def test_ordinary_words_sharing_a_stem_are_untouched(name: str, words: list[str]) -> None:
    text = ", ".join(words)
    assert mask_names(text, [name]) == text


def test_marker_is_not_masked_by_a_later_name() -> None:
    assert mask_names("Миша и Player", ["Миша", "Player"]) == "(player) и (player)"


@pytest.mark.parametrize(
    ("text", "name"),
    [
        (unicodedata.normalize("NFD", "Артём пришёл"), "Артём"),
        ("Артём пришёл", unicodedata.normalize("NFD", "Артём")),
        (unicodedata.normalize("NFD", "Йоко тут"), "Йоко"),
    ],
)
def test_decomposed_forms_are_masked_and_output_is_nfc(text: str, name: str) -> None:
    got = mask_names(text, [name])
    assert got.startswith("(player)") and unicodedata.is_normalized("NFC", got)

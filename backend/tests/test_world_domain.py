import re
from uuid import uuid4

import pytest

from app.domain.world import description_names, scrub, title_names_nobody
from app.domain.world_fallback import fallback_world


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


@pytest.mark.parametrize("genre", ["fairy_tale", "space", "pirates", "custom"])
@pytest.mark.parametrize("locale", ["ru", "en", "es", "zh-CN"])
def test_fallback_world_reads_well_for_one_player_or_several(genre: str, locale: str) -> None:
    world = fallback_world(genre, locale, [uuid4(), uuid4()])
    texts = [world.title, world.setting, world.prologue, *(h.hero_class for h in world.heroes)]
    texts += [x for loc in world.locations for x in (loc.name, loc.description)]
    blob = " ".join(texts).lower()
    for banned in (
        "семь",
        "экипаж",
        "команд ",
        "family",
        "crew",
        "tidying",
        "уборка",
        "famil",
        "tripulaci",
        "家人",
        "家庭",
        "船员",
        "机组",
    ):
        assert banned not in blob
    assert not re.search(r"\bты\b", blob)
    descriptions = [loc.description for loc in world.locations]
    assert len(set(descriptions)) == len(descriptions)
    assert all(loc.name not in loc.description for loc in world.locations)
    assert all(world.setting not in d for d in descriptions)


@pytest.mark.parametrize("locale", ["ru", "en", "es", "zh-CN"])
def test_fallback_world_is_in_the_requested_locale_with_a_hero_per_member(locale: str) -> None:
    ids = [uuid4(), uuid4(), uuid4(), uuid4()]
    world = fallback_world("fairy_tale", locale, ids)
    assert [h.member_id for h in world.heroes] == ids
    assert all(h.hero_class and h.trait and h.skill for h in world.heroes)
    script = {
        "ru": r"[а-яё]",
        "en": r"^[A-Za-z ,.\-']+$",
        "es": r"[áéíóúñ¿¡]",
        "zh-CN": r"[\u4e00-\u9fff]",
    }
    assert re.search(script[locale], world.title + world.setting + world.tone, re.I)
    assert world.tone != fallback_world("fairy_tale", "en", ids).tone or locale == "en"


def test_scrub_removes_a_spanish_name_like_an_english_one() -> None:
    assert scrub("María y Luis viajan con maría", ["María"]) == "y Luis viajan con"
    assert description_names("Mi perro se llama Rocío. Vive en Sevilla") == ["Rocío", "Sevilla"]


def test_description_names_do_not_detect_chinese_names_known_gap() -> None:
    """KNOWN GAP: Chinese has no capitals and no spaces, so a name inside a description is not
    detected, and a cover prompt cannot ban it; known member names are scrubbed by substring."""
    assert description_names("我家的小狗叫旺财，我们住在杭州") == []
    assert scrub("小明在北京玩", ["小明"]) == "在北京玩"
    assert scrub("小明 在北京玩", ["小明"]) == "在北京玩"


def test_chinese_member_name_inside_a_title_is_not_public() -> None:
    assert not title_names_nobody("小明的童话谷", ["小明"])
    assert title_names_nobody("童话谷", ["小明"])


def test_chinese_title_sharing_a_bigram_with_the_description_is_not_public() -> None:
    description = "我家的小狗叫旺财，我们住在杭州"
    assert not title_names_nobody("旺财的杭州冒险", [], description)
    assert title_names_nobody("童话谷", [], description)


def test_chinese_single_character_name_is_not_matched_by_substring() -> None:
    assert title_names_nobody("光明谷", ["明"])


@pytest.mark.parametrize(
    ("text", "words"),
    [
        ("Наша дача в Комарово, рыжий кот Барсик", ["Комарово", "Барсик", "Комаров"]),
        ("город на спинах улиток", []),
        ("Город улиток. Там живёт Лиза! Она добрая", ["Лиза", "Лиз"]),
        ("Мир\nгде Рим и Ай", ["Рим", "Ай"]),
    ],
)
def test_description_names_are_the_capitalised_words_inside_sentences(
    text: str, words: list[str]
) -> None:
    assert description_names(text) == words


def test_scrub_with_description_names_matches_inflections_and_the_base_form() -> None:
    banned = description_names("Дача в Комарово, кот Барсика")
    assert scrub("Барсик и Барсиком в Комарово", banned) == "и в"
    assert scrub("улитки и маяк", banned) == "улитки и маяк"


def test_title_with_a_description_name_is_not_public_but_a_plain_world_is() -> None:
    names = description_names("Наша дача в Комарово, рыжий кот Барсик")
    assert not title_names_nobody("Барсик и тайна маяка", names)
    assert title_names_nobody("Город улиток", description_names("город на спинах улиток"))


@pytest.mark.parametrize(
    ("description", "title"),
    [
        ("мы с котом Барсиком", "Барсик и тайна маяка"),
        ("гуляем с Машей", "Маша и маяк"),
        ("играем с Лизой", "Лиза у моря"),
        ("дача у Комарова", "Комаров и маяк"),
        ("пришла Мария", "Мария у моря"),
        ("пришла Мария", "Сад Марии"),
        ("к нам пришёл Илья", "Илья и маяк"),
        ("к нам пришёл Илья", "Остров Ильи"),
        ("друг Сергей", "Подарок для Сергея"),
        ("друг Алексей", "Тайна Алексея"),
        ("тётя Наталья", "Сад Натальи"),
        ("гуляем с Аней", "Аня у моря"),
        ("играем с Олей", "Оля и маяк"),
        ("играем с Зоей", "Зоя у моря"),
        ("играем с Мией", "Мия у моря"),
        ("играем с Майей", "Майя у моря"),
    ],
)
def test_a_case_form_in_the_description_bans_the_base_form_in_a_title(
    description: str, title: str
) -> None:
    assert not title_names_nobody(title, description_names(description))


@pytest.mark.parametrize(
    ("member", "title"),
    [
        ("Соня", "Сон у моря"),
        ("Мира", "Мир чудес"),
        ("Света", "Свет маяка"),
        ("Надя", "Над морем"),
        ("Боря", "Сосновый бор"),
    ],
)
def test_a_member_name_does_not_drop_a_common_noun_title(member: str, title: str) -> None:
    assert title_names_nobody(title, [member])


def test_a_name_seen_mid_sentence_also_bans_its_sentence_initial_use() -> None:
    names = description_names("Барсик живёт на даче. Мы любим Барсика.")
    assert not title_names_nobody("Барсик и маяк", names)
    assert title_names_nobody("Город улиток", description_names("Город на спинах улиток."))


def test_a_name_that_only_opens_a_sentence_is_not_banned_known_gap() -> None:
    """Known gap: nothing marks it as a name; the adult sees the title in the preview."""
    assert description_names("Барсик живёт на даче.") == []


def test_scrub_removes_every_form_of_a_description_name_ending_in_a_vowel() -> None:
    names = description_names("у нас Мария и Илья")
    assert scrub("Сад Марии, где живёт Мария", names) == "Сад, где живёт"
    assert scrub("Остров Ильи и Илья", names) == "Остров и"


@pytest.mark.parametrize(
    ("description", "title"),
    [
        ("играем с Зоей", "За морем"),
        ("играем с Зоей", "Зов моря"),
        ("играем с Мией", "Мы и маяк"),
    ],
)
def test_a_short_name_form_does_not_drop_a_title_with_a_common_word(
    description: str, title: str
) -> None:
    assert title_names_nobody(title, description_names(description))
    assert scrub("За морем мы видим зов маяка", description_names(description)) == (
        "За морем мы видим зов маяка"
    )


@pytest.mark.parametrize("members", [1, 3])
@pytest.mark.parametrize("genre", ["fairy_tale", "space", "pirates"])
def test_spanish_fallback_world_is_neutral_for_one_player_or_a_group(
    genre: str, members: int
) -> None:
    world = fallback_world(genre, "es", [uuid4() for _ in range(members)])
    blob = f"{world.prologue} {world.setting} " + " ".join(
        loc.description for loc in world.locations
    )
    assert not re.search(r"\b(te|tus?|puedes|tienes|los espera|pueden)\b", blob, re.I)
    assert "espera a quien llegue" in world.prologue


def test_chinese_part_of_a_mixed_banned_string_is_matched_as_a_substring() -> None:
    assert not title_names_nobody("小明的童话谷", ["小明 Wang"])
    assert "小明" not in scrub("小明在北京玩", ["小明 Wang"])

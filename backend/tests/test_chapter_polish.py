"""Chapter validity from the 17.11 live run: whole sentences, no heading line, prompt clauses."""

import pytest
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from app.agent.chapter_writer import (
    INSTRUCTIONS,
    ChapterSpec,
    ChapterWriter,
    build_chapter_writer,
    clean_line,
    drop_adult_escort,
    ends_sentence,
    repeats_quest,
    strip_heading,
)
from app.agent.story_rules import BEAT_RULES
from app.services.cover_prompt import SAFETY_ENDING
from tests.test_chapter_worker import CHAPTER, make_settings

# Real strings from the zh-CN live run (chapters-zh.json, chapters 2 and 6).
ZH_CUT = "掌柜把地图上那段弯路留给了你们。请用家里现有的纸或硬纸板，画或写一块小牌子，上面是"
ZH_FULL = ZH_CUT + "萤火巷三个字。"
ZH_HEADING = "第二章·灯罩上的三样气味"
ZH_STORY = "你们把橘子皮、湿木头和洗好的衣服这三个名字带回茶馆时，灯罩还在柜台上。"


@pytest.mark.parametrize(
    "text",
    [
        "The harbor glowed.",
        "Did it glow?",
        "It glowed!",
        "It glowed…",
        "It glowed...",
        'She said: "It glows."',
        "She said: «It glows.»",
        "（灯亮了。）",
        "掌柜说：「灯亮了。」",
        "灯亮了。”",
        "灯亮了！",
        "¿Brilla la lámpara?",
        "¡Brilla la lámpara!",
        "Тихо светилась лампа.\n",
        "¡Hasta mañana, valientes! 🌟",
        "Tap tap tap... 🐾",
        "— Пора! — сказала сова: „Идём!“",
        "门后传来一阵歌声～",
        "Hasta mañana. 👩‍👧 ",
    ],
)
def test_whole_sentences_end_properly(text: str) -> None:
    assert ends_sentence(text)


@pytest.mark.parametrize(
    "text",
    [
        ZH_CUT,
        "The lamp is on the",
        "Brilla la lámpara,",
        "Лампа светила и",
        "灯亮了，",
        "Lamp:",
        "Лампа светила и 🌟",
        "",
    ],
)
def test_cut_text_does_not_end_properly(text: str) -> None:
    assert not ends_sentence(text)


@pytest.mark.parametrize(
    ("body", "title"),
    [
        (f"{ZH_HEADING}\n\n{ZH_STORY}", "灯罩上的三样气味"),
        (f"灯罩上的三样气味\n\n{ZH_STORY}", "灯罩上的三样气味"),
        (f"# The Lantern\n\n{ZH_STORY}", "The Lantern"),
        (f"Chapter 4\n\n{ZH_STORY}", "The Lantern"),
        (f"Глава пятая\n\n{ZH_STORY}", "Фонарь"),
        (f"Capítulo 2: La linterna\n\n{ZH_STORY}", "La linterna"),
        (f"Глава шестая\n\n{ZH_STORY}", "Фонарь"),
        (f"Chap. 3\n\n{ZH_STORY}", "Фонарь"),
        (f"Chapter XII\n\n{ZH_STORY}", "Фонарь"),
        (f"Глава\n\n{ZH_STORY}", "Фонарь"),
        (f"Глава третья\n\n{ZH_STORY}", "Фонарь"),
        (f"Глава третья: Фонарь\n\n{ZH_STORY}", "Фонарь"),
        (f"Глава двадцать третья\n\n{ZH_STORY}", "Фонарь"),
        (f"Глава пятидесятая\n\n{ZH_STORY}", "Фонарь"),
        (f"Chapter Sixty\n\n{ZH_STORY}", "Фонарь"),
        (f"Chapter One Hundred\n\n{ZH_STORY}", "Фонарь"),
        (f"Chapter Fourteenth\n\n{ZH_STORY}", "Фонарь"),
        (f"Chapter Ninetieth\n\n{ZH_STORY}", "Фонарь"),
        (f"Глава 1 «Фонарь»\n\n{ZH_STORY}", "Фонарь"),
        (f"## Глава 3 «Фонарь»\n\n{ZH_STORY}", "Фонарь"),
        (f"Глава 1 (Фонарь)\n\n{ZH_STORY}", "Фонарь"),
        (f"Chapter 1 The Lantern\n\n{ZH_STORY}", "Фонарь"),
        (f"Chapter 1, The Lantern\n\n{ZH_STORY}", "Фонарь"),
        (f"Глава первая, в которой всё началось\n\n{ZH_STORY}", "Фонарь"),
        (f"Глава пятая!\n\n{ZH_STORY}", "Фонарь"),
        (f"Chapter 3!\n\n{ZH_STORY}", "Фонарь"),
        (f"Глава 7 / Фонарь\n\n{ZH_STORY}", "Фонарь"),
        (f"Глава последняя\n\n{ZH_STORY}", "Фонарь"),
        (f"Capítulo final\n\n{ZH_STORY}", "Фонарь"),
        (f"Глава 7:\n\n{ZH_STORY}", "Фонарь"),
        (f"Глава 7: Фонарь\n\n{ZH_STORY}", "Фонарь"),
        (f"Глава тринадцатая\n\n{ZH_STORY}", "Фонарь"),
        (f"Chapter Eleven\n\n{ZH_STORY}", "Фонарь"),
        (f"Chapter Twelve\n\n{ZH_STORY}", "Фонарь"),
        (f"Capítulo once\n\n{ZH_STORY}", "Фонарь"),
        (f"Capítulo doce\n\n{ZH_STORY}", "Фонарь"),
        (f"Capítulo uno\n\n{ZH_STORY}", "Фонарь"),
        (f"Chapter One\n\n{ZH_STORY}", "Фонарь"),
        (f"CHAPTER IV\n\n{ZH_STORY}", "Фонарь"),
        (f"第三章\n\n{ZH_STORY}", "Фонарь"),
        (f"第 3 回\n\n{ZH_STORY}", "Фонарь"),
        (f"Глава девятая.\n\n{ZH_STORY}", "Фонарь"),
    ],
)
def test_leading_heading_line_is_dropped(body: str, title: str) -> None:
    assert strip_heading(body, title) == ZH_STORY


@pytest.mark.parametrize(
    "body",
    [
        ZH_STORY,
        "Глава была длинной, и лампа погасла.\n\nТихо.",
        "The Lantern glowed.\n\nOk.",
        "Глава деревни подняла руку:\n\n— Слушайте все! Завтра праздник.",
        "Chap with the lantern waved\n\nThe lamp went out.",
        "Chapter civil war began\n\nThe lamp went out.",
        "Глава одиннадцатого отряда кивнула:\n\n— Слушайте все!",
        "Глава пятерых друзей\n\n— Слушайте все!",
        "Глава шестерых\n\n— Слушайте все!",
        "Chapter tenacity came over him\n\n— Слушайте все!",
        "Chapter one of the night began\n\n— Слушайте все!",
        "Глава кивнула:\n\n— Слушайте все!",
        "Глава улыбнулась.\n\n— Слушайте все!",
        "Глава вздохнула —\n\n— Слушайте все!",
        "Глава рода.\n\n— Слушайте все!",
        "Chapter closed.\n\n— Слушайте все!",
        "Chapter ended:\n\n— Слушайте все!",
        "Глава первая закончилась, и лампа погасла.\n\n— Слушайте все!",
    ],
)
def test_a_story_opening_is_never_dropped(body: str) -> None:
    assert strip_heading(body, "The Lantern") == body


def test_a_body_that_is_only_a_heading_is_kept() -> None:
    assert strip_heading(ZH_HEADING, "灯罩上的三样气味") == ZH_HEADING


def scripted(*variants: dict):
    asked: list[int] = []

    async def script(_messages, info) -> ModelResponse:
        variant = variants[min(len(asked), len(variants) - 1)]
        asked.append(1)
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, variant)])

    return FunctionModel(script), asked


def chapter(**fields) -> dict:
    quest = {**CHAPTER["next_quest"], **fields.pop("quest", {})}
    return {**CHAPTER, **fields, "next_quest": quest}


SPEC = ChapterSpec("zh-CN", "space", "w", None, "t", "d", None, ("adult",), 2)


async def run(*variants: dict, spec: ChapterSpec = SPEC):
    writer = build_chapter_writer(make_settings("postgresql://unused"))
    model, asked = scripted(*variants)
    with writer.agent.override(model=model):
        out, _ = await writer.write(spec)
    return out, len(asked)


async def test_a_cut_quest_description_is_retried_once() -> None:
    cut = chapter(quest={"description": ZH_CUT})
    good = chapter(quest={"description": ZH_FULL})
    out, requests = await run(cut, good)
    assert out.next_quest.description == ZH_FULL and requests == 2


LONG_EN = " ".join(["The crew found it."] * 30)  # 120 words: above the floor of every family


async def test_a_cut_body_is_retried_once() -> None:
    out, requests = await run(
        chapter(body=f"{LONG_EN} The crew found the"), chapter(body=f"{LONG_EN} The crew found it.")
    )
    assert out.body.endswith("The crew found it.") and requests == 2


async def test_a_body_cut_twice_fails_instead_of_being_stored() -> None:
    with pytest.raises(UnexpectedModelBehavior):
        await run(chapter(body=f"{LONG_EN} The crew found the"))


async def test_an_answer_cut_twice_fails_instead_of_being_stored() -> None:
    with pytest.raises(UnexpectedModelBehavior):
        await run(chapter(quest={"description": ZH_CUT}))


async def test_the_heading_line_is_dropped_without_a_retry() -> None:
    story = ZH_STORY * 7  # long enough to clear the length floor
    head = chapter(title="灯罩上的三样气味", body=f"{ZH_HEADING}\n\n{story}")
    out, requests = await run(head)
    assert out.body == story and requests == 1


async def test_the_milestone_and_the_cut_share_one_retry() -> None:
    both = chapter(milestone=None, quest={"description": ZH_CUT})
    good = chapter(milestone="萤火巷亮起了灯。", quest={"description": ZH_FULL})
    out, requests = await run(
        both, good, spec=ChapterSpec("zh-CN", "g", "w", None, "t", "d", None, ("adult",), 3)
    )
    assert out.milestone and requests == 2


def sentence(text: str, start: str) -> str:
    begin = text.index(start)
    return text[begin : text.index(". ", begin) + 2]


@pytest.mark.parametrize(
    ("source", "start", "clause"),
    [
        (
            INSTRUCTIONS,
            "End the chapter on",
            "End the chapter on a thread inside the story world that leads into the next quest "
            "(a need, a question, a sound, a door), told as story and never as an instruction to "
            "the players: the last paragraph never repeats the quest, whose wording lives only "
            "in next_quest, and never closes on an object from an earlier chapter, so that the "
            "player wants the next step. ",
        ),
        (
            INSTRUCTIONS,
            "A quest is doable",
            "A quest is doable today in one sitting and gives a real, visible result: the magic "
            "stays in the story, the task itself is ordinary and real, never something that "
            "takes days or grows by itself. ",
        ),
        (
            INSTRUCTIONS,
            "The data field chapter_number",
            "The data field chapter_number is this chapter's ordinal, for your reference "
            "only: never count chapters, pages, days or turns of play, and use no number "
            "that tracks progress. ",
        ),
        (
            BEAT_RULES,
            "milestone shows",
            "milestone shows something visibly opened, built or saved by the player's deeds, "
            "and the field milestone is one short sentence of at most 80 characters (about ten "
            "words) saying what changed in the world, never a bare name; develop deepens what "
            "exists. ",
        ),
    ],
)
def test_prompt_clause_is_whole(source: str, start: str, clause: str) -> None:
    assert sentence(source, start) == clause


def test_picture_ending_forbids_letters_words_and_any_script() -> None:
    assert (
        "no writing of any script: no letters, no words, no labels, no captions, no signs, "
        "no shop signs, no numbers, no logos, no watermarks, no text on screens, maps, windows "
        "or star charts."
    ) in SAFETY_ENDING


# Real strings from the 17.11 probe (polish-1117): ru-adult chapter 1, zh chapter 6.
RU_DESC = (
    "Возьмите лист бумаги и мелок или карандаш и нарисуйте старый клён: ствол, ветви, трещины "
    "коры. Простая картинка — этого достаточно; она станет первой страницей книги Аглаи."
)
RU_LAST = (
    "Возьмите лист бумаги и мелок или карандаш и нарисуйте старый клён таким, каким вы его "
    "помните: ствол, ветви, трещины коры. Пусть это будет простая картинка — она станет первой "
    "страницей книги Аглаи."
)
ZH_DESC = (
    "在纸上写下三个字的问候，字要大而清楚，不写任何人的姓名、住址或电话。"
    "写好后把纸放在自家窗台或门口，让它替你们先漂过去。"
)
STORY = "Аглая вышла из дупла и прислушалась: где-то за оврагом снова звенела тишина.\n\n"


def test_a_last_paragraph_copying_the_quest_is_caught() -> None:
    assert repeats_quest(STORY + RU_LAST, RU_DESC)
    assert repeats_quest(STORY + ZH_DESC, ZH_DESC)


@pytest.mark.parametrize(
    ("body", "desc"),
    [
        (STORY + "Аглая замерла: за оврагом кто-то стучал в тишине.", RU_DESC),
        (RU_LAST + "\n\n" + "Аглая замерла: за оврагом кто-то стучал.", RU_DESC),  # earlier only
        (STORY + "所以今天还有一件小事值得做：把一句只有三个字的话练熟、写清楚。", ZH_DESC),
        (STORY + "Aglaya", "Dibuja."),  # a description too short to compare
        (RU_LAST + "\n" + "Аглая замерла: за оврагом кто-то стучал.", RU_DESC),  # one newline
        (RU_LAST + "\n \n" + "Аглая замерла: за оврагом кто-то стучал.", RU_DESC),  # blank gap
    ],
)
def test_a_story_ending_is_not_taken_for_the_quest(body: str, desc: str) -> None:
    assert not repeats_quest(body, desc)


async def test_a_body_ending_on_the_quest_is_retried_once() -> None:
    copied = chapter(body=STORY * 10 + RU_LAST, quest={"description": RU_DESC})
    story = chapter(
        body=STORY * 10 + "Аглая замерла: за оврагом кто-то стучал.", quest={"description": RU_DESC}
    )
    out, requests = await run(copied, story)
    assert out.body.endswith("стучал.") and requests == 2


def test_the_bring_an_adult_line_is_withheld_only_from_an_adult_only_group() -> None:
    clause = "When every player is an adult, never tell them to take, call or ask an adult. "
    assert clause in INSTRUCTIONS
    assert INSTRUCTIONS.count("adult goes along") == 1


def test_a_group_of_children_keeps_the_outdoor_adult_line() -> None:
    # Prompt is static: a 6-9 group sees no clause that forbids the adult line for children.
    assert "outdoors with an adult in the text when a child plays" in INSTRUCTIONS
    assert "when none plays" not in INSTRUCTIONS
    assert "never tell the players to take, call or ask an adult" not in INSTRUCTIONS


# Real milestones from the live stand (ru adult, chapters 9 and 12).
LEAKED_QUOTE = ">Две линии сошлись: береговая отметка совпала с отметкой на полу, вахта принята."
CLEAN = "Две линии сошлись: береговая отметка совпала с отметкой на полу, вахта принята."


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        (LEAKED_QUOTE, CLEAN),
        (f"> {CLEAN}", CLEAN),
        (f"## {CLEAN}", CLEAN),
        (f"- {CLEAN}", CLEAN),
        (f"**{CLEAN}**", CLEAN),
        (f"«{CLEAN}»", CLEAN),
        (f'"{CLEAN}"', CLEAN),
        (CLEAN, CLEAN),
        ("Полка истории", "Полка истории"),
        (">", None),
        ("«Сова» и «Ключ»", "«Сова» и «Ключ»"),
        ('"Yes" and "No"', '"Yes" and "No"'),
        ("“Yes” and “No”", "“Yes” and “No”"),
        ("-Снежок-", "-Снежок-"),
        ("* Снежок", "Снежок"),
    ],
)
def test_markdown_markers_are_dropped_from_a_one_line_field(raw: str, clean: str | None) -> None:
    assert clean_line(raw) == clean


async def test_a_leaked_quote_marker_never_reaches_the_stored_milestone() -> None:
    spec = ChapterSpec("ru", "g", "w", None, "t", "d", None, ("adult",), 3)
    out, requests = await run(chapter(milestone=LEAKED_QUOTE, title="> Колокол"), spec=spec)
    assert out.milestone == CLEAN and out.title == "Колокол" and requests == 1


RU_LIVE = (
    "Выйдите во двор и найдите три разных листа. "
    "Если идёте во двор, возьмите с собой взрослого. Принесите их домой!"
)
RU_KEPT = "Выйдите во двор и найдите три разных листа. Принесите их домой!"


@pytest.mark.parametrize(
    ("text", "kept"),
    [
        (RU_LIVE, RU_KEPT),
        (
            "Find three leaves. Ask an adult to come along! Bring them home.",
            "Find three leaves. Bring them home.",
        ),
        (
            "Find three leaves. Take a grown-up with you. Bring them home.",
            "Find three leaves. Bring them home.",
        ),
        ("Find leaves. Call a grown up first? Then go.", "Find leaves. Then go."),
        (
            "Busca tres hojas. Pide a un adulto que te acompañe. Tráelas a casa.",
            "Busca tres hojas. Tráelas a casa.",
        ),
        ("Busca hojas. Llama a una persona mayor… Vuelve a casa.", "Busca hojas. Vuelve a casa."),
        (
            "去院子里找三片叶子。带上一个大人一起去。把叶子带回家。",
            "去院子里找三片叶子。把叶子带回家。",
        ),
        ("找三片叶子！请成年人陪同？带回家。", "找三片叶子！带回家。"),
        ("Первое.\nВозьмите взрослого.\nВторое.", "Первое.\nВторое."),
        ("Возьмите соседку-взрослую. Идите.", "Идите."),
    ],
)
def test_adult_escort_sentences_are_dropped(text: str, kept: str) -> None:
    assert drop_adult_escort(text) == kept


@pytest.mark.parametrize(
    "text",
    ["Возьмите взрослого с собой.", "Take an adult along.", "带上大人。"],
)
def test_a_description_that_is_only_the_escort_stays(text: str) -> None:
    assert drop_adult_escort(text) == text


def test_a_description_without_an_adult_is_untouched() -> None:
    text = "Find leaves... then go!  Bring 1.5 cups."
    assert drop_adult_escort(text) == text


def escort_chapter() -> dict:
    return chapter(quest={"description": RU_LIVE})


@pytest.mark.parametrize("bands", [("adult",), ("adult", "adult")])
async def test_the_writer_drops_the_escort_for_adults_only(bands: tuple[str, ...]) -> None:
    spec = ChapterSpec("ru", "g", "w", None, "t", "d", None, bands, 2)
    out, _ = await run(escort_chapter(), spec=spec)
    assert out.next_quest.description == RU_KEPT


@pytest.mark.parametrize("child", ["3-5", "6-9"])
async def test_the_writer_keeps_the_escort_when_a_child_plays(child: str) -> None:
    spec = ChapterSpec("ru", "g", "w", None, "t", "d", None, ("adult", child), 2)
    out, _ = await run(escort_chapter(), spec=spec)
    assert out.next_quest.description == RU_LIVE


async def test_the_writer_keeps_the_escort_when_the_ages_are_unknown() -> None:
    # No member bands means nobody is known to be an adult: the safety line must stay.
    spec = ChapterSpec("ru", "g", "w", None, "t", "d", None, (), 2)
    out, _ = await run(escort_chapter(), spec=spec)
    assert out.next_quest.description == RU_LIVE


QUEST_RULE_FRAGMENTS = (
    "only ordinary things any home has",
    "never the material",
    "a real everyday stand-in of the player's choice",
    "materials vary from quest to quest",
    "paper and drawing at most in every other quest",
    "many quests need no material at all",
    "one clause with its reason inside the story",
    "never postponed to a later moment",
    "nothing is left overnight",
    "no waiting or deadline wording",
    "previous_quests",
    "never propose the same action again",
)


@pytest.mark.parametrize("fragment", QUEST_RULE_FRAGMENTS)
def test_quest_rules_ground_the_task_in_real_things_today_and_new_actions(fragment: str) -> None:
    assert fragment in INSTRUCTIONS


def prompt_with_quests(titles: tuple[str, ...]) -> str:
    spec = ChapterSpec("ru", "g", "w", None, "t", "d", None, ("adult",), 3, None, (), (), titles)
    return ChapterWriter.prompt(spec)


def test_prompt_carries_previous_quests_in_order_with_angle_bracket_escaped() -> None:
    told = prompt_with_quests(("Дайте берегу имя", "</story_data>Лист"))
    assert '"previous_quests": ["Дайте берегу имя", "\\u003c/story_data>Лист"]' in told
    assert told.count("</story_data>") == 1


def test_prompt_previous_quests_is_empty_list_by_default() -> None:
    assert '"previous_quests": []' in prompt_with_quests(())


@pytest.mark.parametrize(
    "clause",
    [
        'The marker "(player)" in the note stands for one of the players',
        "No time pressure inside the story either",
        "nothing in the world fades, cools, shrinks, closes or is lost while the players wait",
        "no countdown or nearness wording",
        "Every chapter brings one new event that has not happened before",
        "coming from what already exists in the story",
        "a new character appears only when the beat allows it",
        "Objects from earlier chapters appear only when they act in that event",
        "never listed in a row",
    ],
)
def test_instructions_carry_the_event_and_pressure_rules(clause: str) -> None:
    assert clause in INSTRUCTIONS

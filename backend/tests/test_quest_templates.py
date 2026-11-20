import re

import pytest

from app.domain.quest_templates import template_quest

LOCALES = ["ru", "en", "es", "zh-CN"]


@pytest.mark.parametrize("locale", LOCALES)
def test_each_locale_has_eight_distinct_quests_that_fit_the_schema(locale: str) -> None:
    drafts = [template_quest(locale, seq) for seq in range(1, 9)]
    assert len({d.title for d in drafts}) == 8
    assert all(1 <= len(d.title) <= 80 and 1 <= len(d.description) <= 400 for d in drafts)
    assert template_quest(locale, 9) == drafts[0]


_GROUP_WORDING = re.compile(
    r"famil|someone at home|family member|семь|близк|кого-нибудь дома"
    r"|alguien en casa|家人|家庭|一家",
    re.I,
)


@pytest.mark.parametrize("locale", LOCALES)
def test_template_quests_do_not_presume_a_group_or_a_family(locale: str) -> None:
    for seq in range(1, 9):
        d = template_quest(locale, seq)
        assert not _GROUP_WORDING.search(f"{d.title} {d.description}"), d.description


def test_spanish_quests_use_the_impersonal_infinitive_not_tu() -> None:
    for seq in range(1, 9):
        d = template_quest("es", seq).description
        assert re.match(r"[A-ZÁÉÍÓÚ]\w+(ar|er|ir)\b", d), d
        assert not re.search(r"\b(te|tu|tus|ti)\b", d, re.I), d

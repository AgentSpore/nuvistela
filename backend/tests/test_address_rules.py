import pytest

from app.agent.address_rules import ADDRESS_RULES


@pytest.mark.parametrize(
    "mapping",
    [
        '"usted" for one adult playing alone',
        '"ustedes" when several play (any ages)',
        '"tú" for one player under 18 (age band 3-5, 6-9, 10-13 or 14-17) playing alone',
        "never a gendered adjective, participle or pronoun about the players",
        "no mismo/a, solo/a, listo/a, cansado/a, bienvenido/a",
        "您 for one adult playing alone",
        "你 for one player under 18 playing alone",
        "你们 or 大家 when several play (any ages), never 您们",
        "one form in the whole answer, never mixed",
        '"вы" for one adult playing alone and whenever several play (any ages)',
        '"ты" for one player under 18 (age band 3-5, 6-9, 10-13 or 14-17) playing alone',
        "use one of them in the whole answer, never both",
        "never a gendered past-tense verb, short adjective or participle about the player",
        '(no "ты сделал/сделала", "готов/готова"; "вы сделали" is fine)',
        '"получилось", "всё готово"',
    ],
)
def test_address_rules_state_each_mapping(mapping: str) -> None:
    assert mapping in ADDRESS_RULES
    assert ADDRESS_RULES.count(mapping) == 1


def test_address_rules_apply_to_every_field() -> None:
    assert "in every field you write" in ADDRESS_RULES

"""Masks the players' real names in free text before it reaches the model."""

import re
import unicodedata
from functools import cache

PLAYER_MARKER = "(player)"
_CJK = re.compile(r"[぀-ヿ㐀-鿿가-힯]")
_HAN_ONLY = re.compile(r"[㐀-鿿]+")
_CYRILLIC = re.compile(r"[а-я]")
_NAME_PARTS = re.compile(r"[\s-]+")
# Case endings by the last letter of a folded name; the stem is the name minus that letter.
_ENDINGS = {
    "а": "а|ы|и|е|у|ой|ою|ей|ею",
    "я": "я|и|е|ю|ей|ею",
    "й": "й|я|ю|е|ем",
    "ь": "ь|я|ю|е|ем",
}
_CONSONANT_ENDINGS = "а|у|ом|ем|е|ы|и|ой|ей"
_SHORT_CONSONANT_ENDINGS = "а|у|ом|ем|ы|и|ей"  # Лев: левой, леве are ordinary words
_VOWEL_FINAL = "аяьйоеиыуюэ"
_DIMINUTIVES = "к|еньк|уш|юш|аш"  # Миша -> Мишка, Саша -> Сашенька, Илья -> Ильюша
_DIMINUTIVE_ENDINGS = "а|и|е|у|я|ю|ой|ою|ей|ею"


@cache
def _fold_char(c: str) -> str:
    """One char, lower-case, ё as е, Latin accents dropped; always exactly one char back."""
    if c in "йЙ":
        return "й"
    if c in "ёЁ":
        return "е"
    base = c
    if "LATIN" in unicodedata.name(c, ""):
        plain = "".join(x for x in unicodedata.normalize("NFD", c) if not unicodedata.combining(x))
        base = plain if len(plain) == 1 else c
    low = base.lower()
    return low if len(low) == 1 else base


def _nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def _fold(text: str) -> str:
    return "".join(map(_fold_char, text))


def _cyrillic_pattern(token: str) -> str:
    last, stem = token[-1], re.escape(token[:-1])
    if last in _ENDINGS:
        pattern = rf"{stem}(?:{_ENDINGS[last]})"
        if last in "ая":
            pattern += rf"|{stem}(?:{_DIMINUTIVES})(?:{_DIMINUTIVE_ENDINGS})"
        return pattern
    if last in _VOWEL_FINAL:
        return re.escape(token)
    endings = _CONSONANT_ENDINGS if len(token) > 3 else _SHORT_CONSONANT_ENDINGS
    return rf"{re.escape(token)}(?:{endings})?"


def _pattern(token: str) -> str:
    """Alternative matching one folded name word, with its case and diminutive forms."""
    if _CJK.search(token):
        return re.escape(token)
    if len(token) < 3:
        body = re.escape(token)
    elif _CYRILLIC.search(token):
        body = _cyrillic_pattern(token)
    else:
        body = rf"{re.escape(token)}(?:s|es)?"  # Bobbys, Marias; a possessive 's stays outside
    return rf"(?<!\w)(?:{body})(?!\w)"


def _tokens(names: list[str]) -> set[str]:
    words = {w for name in names for w in _NAME_PARTS.split(_fold(_nfc(name))) if len(w) > 1}
    # a Han name starts with one or two family-name characters: 王小明 is also called 小明
    han = [w for w in words if _HAN_ONLY.fullmatch(w)]
    return words | {w[1:] for w in han if len(w) > 2} | {w[2:] for w in han if len(w) > 3}


def mask_names(text: str, names: list[str]) -> str:
    """Replace every form of every name with `(player)`.

    Text and names are NFC-normalized, so a decomposed ё or й from copy-paste matches. A name
    is split into words at spaces and hyphens and matched on a folded copy of the text (case,
    ё/е and Latin accents ignored; the copy has the text's length, so spans map back).
    Cyrillic names of 3+ letters match with a closed set of case endings chosen by the last
    letter, plus diminutives (Миша: Мишка, Саша: Сашенька); a diminutive of an ordinary word,
    such as the toy мишка, is masked on purpose: a leaked name costs more than a lost word.
    Stem changes (Лев -> Льва) are missed. Latin names match with an optional s/es ending
    (Bobbys; a possessive 's stays outside the match); 2-letter names match as whole words.
    CJK names match as a substring; a Han-only name also matches without its
    first one or two (family-name) characters, kana and Hangul names do not.
    """
    tokens = _tokens(names)
    if not tokens:
        return text
    text = _nfc(text)
    pattern = "|".join(_pattern(t) for t in sorted(tokens, key=len, reverse=True))
    out, pos = [], 0
    for found in re.finditer(pattern, _fold(text)):
        out += [text[pos : found.start()], PLAYER_MARKER]
        pos = found.end()
    return "".join(out) + text[pos:]

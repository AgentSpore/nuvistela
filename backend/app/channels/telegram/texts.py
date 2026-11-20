"""Every bot reply, in the player's language."""

import re

LOCALES = ("ru", "en", "es", "zh-CN")
_FALLBACK = "en"
_TELEGRAM_LANGUAGES = {"ru": "ru", "es": "es", "zh": "zh-CN"}
_ON = {
    "ru": "Напоминания включены: напишу, когда будет готова глава, и вечером, если задание ждёт.",
    "en": (
        "Reminders are on: I'll write when a chapter is ready and in the evening if a quest waits."
    ),
    "es": (
        "Recordatorios activados: escribiré cuando un capítulo esté listo"
        " y por la tarde si una misión espera."
    ),
    "zh-CN": "提醒已开启：章节完成时，以及傍晚有任务等待时，我会通知你。",
}
_OFF = {
    "ru": "Напоминания выключены.",
    "en": "Reminders are off.",
    "es": "Recordatorios desactivados.",
    "zh-CN": "提醒已关闭。",
}
_USAGE = {
    "ru": "Напоминания {state}. Включить: /notify on, выключить: /notify off.",
    "en": "Reminders are {state}. Turn on: /notify on, turn off: /notify off.",
    "es": "Los recordatorios están {state}. Activar: /notify on, desactivar: /notify off.",
    "zh-CN": "提醒当前{state}。开启：/notify on，关闭：/notify off。",
}
_STATE = {
    True: {"ru": "включены", "en": "on", "es": "activados", "zh-CN": "已开启"},
    False: {"ru": "выключены", "en": "off", "es": "desactivados", "zh-CN": "已关闭"},
}
_TEXTS = {
    "linked": {
        "ru": "Чат подключён.",
        "en": "connected",
        "es": "Chat conectado.",
        "zh-CN": "聊天已连接。",
    },
    "bad_code": {
        "ru": "Код недействителен или истёк.",
        "en": "code invalid or expired",
        "es": "El código no es válido o ya caducó.",
        "zh-CN": "验证码无效或已过期。",
    },
    "not_admin": {
        "ru": "Подключить чат могут только его администраторы.",
        "en": "only chat admins can link",
        "es": "Solo los administradores del chat pueden conectarlo.",
        "zh-CN": "只有聊天管理员才能连接。",
    },
    "try_later": {
        "ru": "Не получилось. Попробуйте чуть позже.",
        "en": "try again later",
        "es": "No se pudo. Inténtalo de nuevo más tarde.",
        "zh-CN": "暂时无法完成，请稍后再试。",
    },
    "no_answer": {
        "ru": "Ведущий не нашёл, что ответить. Попробуйте ещё раз.",
        "en": "the game master had no answer, try again",
        "es": "El narrador no tuvo respuesta. Inténtalo de nuevo.",
        "zh-CN": "故事引导员没有回应，请再试一次。",
    },
    "empty_question": {
        "ru": "Напишите вопрос после /ask.",
        "en": "write a question after /ask",
        "es": "Escribe una pregunta después de /ask.",
        "zh-CN": "请在 /ask 后面写下你的问题。",
    },
    "busy": {
        "ru": "Подождите, я ещё отвечаю.",
        "en": "wait, I'm still answering",
        "es": "Espera, todavía estoy respondiendo.",
        "zh-CN": "请稍等，我还在回答。",
    },
    "limit": {
        "ru": "На сегодня лимит исчерпан.",
        "en": "daily limit reached",
        "es": "Se alcanzó el límite diario.",
        "zh-CN": "今天的额度已用完。",
    },
    "down": {
        "ru": "Ведущий сейчас недоступен.",
        "en": "game master unavailable",
        "es": "El narrador no está disponible ahora.",
        "zh-CN": "故事引导员暂时不可用。",
    },
    "too_long": {
        "ru": "Сообщение слишком длинное (не больше {limit} символов).",
        "en": "message too long (max {limit} characters)",
        "es": "El mensaje es demasiado largo (máximo {limit} caracteres).",
        "zh-CN": "消息太长（最多 {limit} 个字符）。",
    },
    "unlinked": {
        "ru": "Сначала подключите этот чат: возьмите код на сайте и отправьте {command} <код>.",
        "en": "link this chat first: {command} <code> from the site",
        "es": "Primero conecta este chat: copia el código del sitio y envía {command} <código>.",
        "zh-CN": "请先连接此聊天：在网站上获取验证码，然后发送 {command} <验证码>。",
    },
}
TABLES = (_ON, _OFF, _USAGE, *_STATE.values(), *_TEXTS.values())


def locale_from_language_code(code: str | None) -> str:
    """Locale for a Telegram `language_code` such as `es-419` or `zh-hans`; None or unknown: en."""
    primary = re.split(r"[-_]", (code or "").lower())[0]
    return _TELEGRAM_LANGUAGES.get(primary, _FALLBACK)


def localized(key: str, locale: str, **values: object) -> str:
    table = _TEXTS[key]
    return table.get(locale, table[_FALLBACK]).format(**values)


def notify_changed(locale: str, on: bool) -> str:
    table = _ON if on else _OFF
    return table.get(locale, table[_FALLBACK])


def notify_status(locale: str, on: bool) -> str:
    state = _STATE[on]
    lang = locale if locale in state else _FALLBACK
    return _USAGE[lang].format(state=state[lang])

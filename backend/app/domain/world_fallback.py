"""Template worlds shown when generation fails three times (W-1). Texts per genre and locale.

The player reads these on screen, for one person or several, adult or child: nothing here assumes
a gender, a family or a crew, and Russian addresses the player as «вы».
"""

from uuid import UUID

from app.domain.world import Hero, Location, World

_CLASSES = {
    "ru": ("Искра затеи", "Душа затеи", "Опора пути"),
    "en": ("Pathfinder", "Helper", "Dreamer"),
    "es": ("Chispa de ideas", "Alma de la aventura", "Apoyo del camino"),
    "zh-CN": ("探路者", "热心人", "追梦者"),
}
_TRAITS = {
    "ru": ("любопытство", "доброта", "выдумка"),
    "en": ("curious", "kind", "inventive"),
    "es": ("curiosidad", "bondad", "ingenio"),
    "zh-CN": ("好奇", "善良", "巧思"),
}
_TONE = {"ru": "тёплый", "en": "warm", "es": "cálido", "zh-CN": "温暖"}
_SKILLS = {
    "ru": ("наблюдательность", "забота", "находчивость"),
    "en": ("noticing", "caring", "resourcefulness"),
    "es": ("observación", "cuidado", "inventiva"),
    "zh-CN": ("观察", "关怀", "机智"),
}
# (title, setting, prologue, ((place, description) x 4)) by genre, then locale.
_TEXT = {
    "fairy_tale": {
        "ru": (
            "Сказочная долина",
            "Долина, где живут добрые чудеса",
            "В долине зажглись первые огоньки, и она ждёт вас. "
            "Первое дело совсем рядом, и начать его можно сегодня.",
            (
                ("Сказочная поляна", "Здесь по утрам просыпаются светлячки и звенят колокольчики."),
                ("Хрустальный ручей", "Ручей поёт тихую песню и хранит блестящие камешки."),
                ("Старая мельница", "На мельнице давно никто не жил, но в окошке мерцает свет."),
                ("Тайный сад", "Среди цветов спрятаны тропинки, которые видно не сразу."),
            ),
        ),
        "en": (
            "Fairy Valley",
            "A valley where kind wonders live",
            "The first lights have come on in the valley, and it is waiting for you. "
            "The first task is close by, and you can begin it today.",
            (
                ("Fairy Meadow", "Fireflies wake here each morning and the bluebells ring."),
                ("Crystal Brook", "The brook hums a quiet tune and keeps shiny pebbles."),
                ("Old Mill", "Nobody has lived in the mill for years, yet a light glows inside."),
                ("Secret Garden", "Paths hide among the flowers and show up only to the patient."),
            ),
        ),
        "es": (
            "Valle de Cuento",
            "Un valle donde viven maravillas amables",
            "En el valle se han encendido las primeras luces y espera a quien llegue. "
            "La primera tarea está muy cerca, y se puede empezar hoy.",
            (
                (
                    "Prado del Cuento",
                    "Aquí despiertan cada mañana las luciérnagas y suenan las campanillas.",
                ),
                (
                    "Arroyo de Cristal",
                    "El arroyo canturrea una melodía suave y guarda piedrecitas brillantes.",
                ),
                (
                    "Molino Viejo",
                    "Hace años que nadie vive en el molino, pero una luz brilla en la ventana.",
                ),
                (
                    "Jardín Secreto",
                    "Entre las flores se esconden senderos que solo se dejan ver con paciencia.",
                ),
            ),
        ),
        "zh-CN": (
            "童话谷",
            "一座充满温暖奇迹的山谷",
            "山谷里亮起了第一批小灯，正等待着出发的人。第一件事就在附近，今天就可以开始。",
            (
                ("童话草地", "每天清晨，萤火虫在这里醒来，风铃叮当作响。"),
                ("水晶小溪", "小溪轻轻哼着歌，藏着一颗颗闪亮的小石子。"),
                ("老磨坊", "磨坊多年无人居住，窗里却亮着一盏灯。"),
                ("秘密花园", "花丛间藏着小路，只有耐心的人才看得见。"),
            ),
        ),
    },
    "space": {
        "ru": (
            "Звёздный дом",
            "Станция среди дружелюбных звёзд",
            "Станция проснулась среди звёзд и ждёт вас. "
            "Первое дело совсем рядом, и начать его можно сегодня.",
            (
                ("Рубка станции", "Отсюда видно все ближние звёзды, и каждая подмигивает."),
                ("Оранжерея", "Под тёплой лампой растут растения, которым нужен ваш уход."),
                (
                    "Лунный причал",
                    "К причалу приходят малые корабли с письмами из далёких мест.",
                ),
                ("Обзорная башня", "Из башни можно разглядеть кольца планеты и хвосты комет."),
            ),
        ),
        "en": (
            "Star Home",
            "A station among friendly stars",
            "The station has woken up among the stars and is waiting for you. "
            "The first task is close by, and you can begin it today.",
            (
                ("Control Room", "Every nearby star can be seen from here, and each one winks."),
                ("Greenhouse", "Plants grow under a warm lamp and they need your care."),
                ("Moon Dock", "Little ships bring letters from faraway places to this dock."),
                ("Lookout Tower", "From the tower you can spot planet rings and comet tails."),
            ),
        ),
        "es": (
            "Hogar de Estrellas",
            "Una estación entre estrellas amistosas",
            "La estación ha despertado entre las estrellas y espera a quien llegue. "
            "La primera tarea está muy cerca, y se puede empezar hoy.",
            (
                (
                    "Sala de Control",
                    "Desde aquí se ven todas las estrellas cercanas, y cada una guiña un ojo.",
                ),
                (
                    "Invernadero",
                    "Bajo una lámpara cálida crecen plantas que necesitan cuidados.",
                ),
                ("Muelle Lunar", "Pequeñas naves traen a este muelle cartas de lugares lejanos."),
                (
                    "Torre Mirador",
                    "Desde la torre se ven los anillos de los planetas y las colas de los cometas.",
                ),
            ),
        ),
        "zh-CN": (
            "星之家",
            "一座位于友好群星之间的空间站",
            "空间站在群星之间醒来，正等待着出发的人。第一件事就在附近，今天就可以开始。",
            (
                ("控制室", "从这里能看到附近所有的星星，每一颗都在眨眼。"),
                ("温室", "暖灯下长着一些植物，它们需要照料。"),
                ("月球码头", "小飞船把来自远方的信件送到这座码头。"),
                ("瞭望塔", "从塔上能望见行星的光环和彗星的尾巴。"),
            ),
        ),
    },
    "pirates": {
        "ru": (
            "Бухта Ветров",
            "Бухта, где паруса хранят тайны",
            "Бухта проснулась и ждёт вас: ветер уже несёт к берегу первую тайну. "
            "Первое дело совсем рядом, и начать его можно сегодня.",
            (
                ("Маяк на скале", "Его луч каждый вечер показывает путь к новым тайнам."),
                ("Ракушечный берег", "Волны выносят сюда ракушки, и в каждой шумит история."),
                (
                    "Старая пристань",
                    "У пристани скрипят доски, а у причалов качаются лодки.",
                ),
                ("Пещера эха", "Если крикнуть в пещере, эхо ответит совсем другими словами."),
            ),
        ),
        "en": (
            "Windy Cove",
            "A cove where sails keep secrets",
            "The cove has woken up, the wind is bringing the first secret to shore, and it is "
            "waiting for you. The first task is close by, and you can begin it today.",
            (
                ("Cliff Lighthouse", "Each evening its beam points the way to new secrets."),
                (
                    "Shell Beach",
                    "The waves leave shells here, and each whispers its own story.",
                ),
                ("Old Pier", "The planks creak and boats with strange flags rock beside it."),
                ("Echo Cave", "Shout into the cave and the echo answers in different words."),
            ),
        ),
        "es": (
            "Bahía de los Vientos",
            "Una bahía donde las velas guardan secretos",
            "La bahía ha despertado, el viento trae a la orilla el primer secreto "
            "y espera a quien llegue. "
            "La primera tarea está muy cerca, y se puede empezar hoy.",
            (
                (
                    "Faro del Acantilado",
                    "Cada tarde su haz señala el camino hacia nuevos secretos.",
                ),
                (
                    "Playa de Conchas",
                    "Las olas dejan aquí conchas, y cada una susurra su propia historia.",
                ),
                (
                    "Muelle Viejo",
                    "Las tablas crujen y junto a él se mecen barcas con banderas extrañas.",
                ),
                (
                    "Cueva del Eco",
                    "Si se grita en la cueva, el eco responde con palabras muy distintas.",
                ),
            ),
        ),
        "zh-CN": (
            "风之湾",
            "一个白帆里藏着秘密的海湾",
            "海湾醒来了，风把第一个秘密吹到岸边，正等待着出发的人。第一件事就在附近，今天就可以开始。",
            (
                ("悬崖灯塔", "每到傍晚，灯塔的光束都会指向新的秘密。"),
                ("贝壳海滩", "海浪把贝壳留在这里，每一只都在低声讲着自己的故事。"),
                ("旧码头", "木板吱吱作响，挂着奇怪旗帜的小船在码头边轻轻摇晃。"),
                ("回声洞", "对着山洞喊一声，回声会用完全不同的话来回答。"),
            ),
        ),
    },
}


def fallback_world(genre: str, locale: str, member_ids: list[UUID]) -> World:
    """A valid World for the genre ('custom' uses the fairy tale) with one hero per member."""
    lang = locale if locale in _CLASSES else "en"
    title, setting, prologue, places = _TEXT.get(genre, _TEXT["fairy_tale"])[lang]
    n = len(_CLASSES[lang])
    return World(
        title=title,
        setting=setting,
        tone=_TONE[lang],
        locations=[Location(name=name, description=text) for name, text in places],
        heroes=[
            Hero(
                member_id=m,
                hero_class=_CLASSES[lang][i % n],
                trait=_TRAITS[lang][i % n],
                skill=_SKILLS[lang][i % n],
            )
            for i, m in enumerate(member_ids)
        ],
        prologue=prologue,
    )

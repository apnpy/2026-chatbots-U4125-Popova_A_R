import json
import logging
import os
import re
from collections import Counter
from pathlib import Path
from random import sample
from typing import Dict, List, Optional, Set
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import Application

app = FastAPI()

from dotenv import load_dotenv
load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN не найден")

application = (
    Application.builder()
    .token(TOKEN)
    .build()
)

@app.on_event("startup")
async def startup():
    await application.initialize()
    await post_init(application)
    await application.start()

@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return {"ok": True}


from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

DATA_FILE = Path("data.json")
RECIPES_FILE = Path("recipes_110_final.json")
PENDING_RECIPE_LIST_KEY = "pending_recipe_list"
# Сколько вариантов показывать в одном списке (инлайн-кнопки не должны разрастаться слишком сильно).
MAX_RECIPES_IN_LIST = 8
LOW_KCAL_MAX = 420
HIGH_PROTEIN_MIN = 25
EXPENSIVE_KEYWORDS = {
    "лосось",
    "говядин",
    "форель",
    "кревет",
    "авокадо",
    "рикотта",
    "моцарел",
    "пармез",
    "кокос",
}


def _extract_json_object(raw: str, opening_brace_idx: int) -> Optional[str]:
    """
    Возвращает JSON-объект из сырой строки начиная с '{'.
    Учитывает строки и экранирование, чтобы корректно найти закрывающую скобку.
    """
    depth = 0
    in_string = False
    escaped = False

    for idx in range(opening_brace_idx, len(raw)):
        ch = raw[idx]
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return raw[opening_brace_idx : idx + 1]
    return None


def _recover_recipes_from_broken_json(raw: str) -> Dict[str, Dict]:
    """
    Восстанавливает рецепты из частично поврежденного JSON-файла.
    Ищет паттерны вида "recipe_id": { ... } и пытается распарсить каждый объект отдельно.
    """
    recovered: Dict[str, Dict] = {}
    for match in re.finditer(r'"([A-Za-z0-9_]+)"\s*:\s*\{', raw):
        recipe_id = match.group(1)
        opening_brace_idx = match.end() - 1
        obj_text = _extract_json_object(raw, opening_brace_idx)
        if not obj_text:
            continue
        try:
            recipe_obj = json.loads(obj_text)
        except json.JSONDecodeError:
            continue
        if isinstance(recipe_obj, dict) and recipe_id not in recovered:
            recovered[recipe_id] = recipe_obj
    return recovered


def _is_valid_recipe(recipe: Dict) -> bool:
    """Минимальная проверка обязательных полей рецепта."""
    required = ("name", "meal", "quick", "time", "ingredients", "steps")
    return all(key in recipe for key in required)


def _coerce_nutrition(recipe: Dict) -> Dict:
    """
    Возвращает корректный блок КБЖУ.
    Если поля нет или формат неверный, ставит безопасные значения-заглушки.
    """
    nutrition = recipe.get("nutrition")
    if not isinstance(nutrition, dict):
        return {"kcal": "—", "protein": "—", "fat": "—", "carbs": "—"}
    return {
        "kcal": nutrition.get("kcal", "—"),
        "protein": nutrition.get("protein", "—"),
        "fat": nutrition.get("fat", "—"),
        "carbs": nutrition.get("carbs", "—"),
    }


def load_recipes() -> Dict[str, Dict]:
    """Загружает рецепты из JSON. При проблемах пытается восстановить максимум данных."""
    if not RECIPES_FILE.exists():
        logger.error("Файл с рецептами не найден: %s", RECIPES_FILE)
        return {}

    try:
        raw = RECIPES_FILE.read_text(encoding="utf-8")
    except OSError as exc:
        logger.error("Не удалось прочитать файл рецептов: %s", exc)
        return {}

    recipes_raw: Dict[str, Dict]
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            recipes_raw = parsed
        elif isinstance(parsed, list):
            recipes_raw = {}
            for chunk in parsed:
                if isinstance(chunk, dict):
                    for key, value in chunk.items():
                        if key not in recipes_raw and isinstance(value, dict):
                            recipes_raw[key] = value
        else:
            logger.error("Неподдерживаемый формат JSON в %s", RECIPES_FILE)
            return {}
    except json.JSONDecodeError as exc:
        logger.warning(
            "JSON поврежден (%s). Пробую восстановить рецепты из фрагментов...", exc
        )
        recipes_raw = _recover_recipes_from_broken_json(raw)

    recipes: Dict[str, Dict] = {}
    for recipe_id, recipe in recipes_raw.items():
        if not isinstance(recipe, dict):
            continue
        if not _is_valid_recipe(recipe):
            logger.warning(
                "Пропущен некорректный рецепт '%s' (не хватает полей)", recipe_id
            )
            continue
        recipe_copy = dict(recipe)
        recipe_copy["servings"] = int(recipe_copy.get("servings", 2))
        recipe_copy["nutrition"] = _coerce_nutrition(recipe_copy)
        recipes[recipe_id] = recipe_copy

    logger.info("Загружено рецептов: %s", len(recipes))
    return recipes


RECIPES = load_recipes()

# Постоянная клавиатура внизу чата — не нужно вводить команды вручную.
MAIN_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton("🌅 Завтрак"),
            KeyboardButton("🍲 Обед"),
            KeyboardButton("🌙 Ужин"),
        ],
        [
            KeyboardButton("⚡ Быстро"),
            KeyboardButton("📆 Меню на день"),
            KeyboardButton("📅 Меню на неделю"),
        ],
        [
            KeyboardButton("🥕 Из продуктов"),
            KeyboardButton("📋 Мой список"),
            KeyboardButton("🛒 Покупки"),
        ],
        [
            KeyboardButton("❤️ Избранное"),
            KeyboardButton("❓ Помощь"),
        ],
        [
            KeyboardButton("🧾 Фильтр"),
            KeyboardButton("🔎 Поиск блюда"),
        ],
    ],
    resize_keyboard=True,
    input_field_placeholder="Выберите действие кнопкой или откройте меню ⌘",
)


def set_pending_recipe_list(context: ContextTypes.DEFAULT_TYPE, recipe_ids: List[str], title: str) -> None:
    """Сохраняет список инлайн-кнопок, чтобы можно было вернуться к нему из карточки рецепта."""
    context.user_data[PENDING_RECIPE_LIST_KEY] = {
        "ids": list(recipe_ids),
        "title": title,
    }


def get_pending_recipe_list(context: ContextTypes.DEFAULT_TYPE) -> Optional[Dict]:
    return context.user_data.get(PENDING_RECIPE_LIST_KEY)


def recipe_action_keyboard(rid: str) -> InlineKeyboardMarkup:
    """Кнопки под открытым рецептом: избранное, список покупок и возврат к списку."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Добавить в избранное ❤️", callback_data=f"fav|{rid}")],
            [InlineKeyboardButton("Добавить в покупки 🛒", callback_data=f"shopadd|{rid}")],
            [InlineKeyboardButton("◀️ К списку рецептов", callback_data="recipeback")],
        ]
    )


def main_menu_inline_keyboard() -> InlineKeyboardMarkup:
    """Компактное меню под первым сообщением (удобно на планшете / узком экране)."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Завтрак", callback_data="nav|breakfast"),
                InlineKeyboardButton("Обед", callback_data="nav|lunch"),
                InlineKeyboardButton("Ужин", callback_data="nav|dinner"),
            ],
            [
                InlineKeyboardButton("Быстро", callback_data="nav|quick"),
                InlineKeyboardButton("Меню день", callback_data="nav|day"),
                InlineKeyboardButton("Меню неделя", callback_data="nav|week"),
            ],
            [
                InlineKeyboardButton("Из продуктов", callback_data="nav|from"),
                InlineKeyboardButton("Мой список", callback_data="nav|list"),
            ],
            [
                InlineKeyboardButton("Покупки", callback_data="nav|shop"),
                InlineKeyboardButton("Избранное", callback_data="nav|favs"),
            ],
            [
                InlineKeyboardButton("Помощь", callback_data="nav|help"),
            ],
            [
                InlineKeyboardButton("Фильтр", callback_data="nav|filter"),
                InlineKeyboardButton("Поиск", callback_data="nav|search"),
            ],
        ]
    )


HELP_TEXT = (
    "📖 <b>Как пользоваться</b>\n\n"
    "Внизу — постоянные кнопки. Ещё удобнее на телефоне: слева от поля ввода меню команд ⌘.\n\n"
    "<b>По-русски:</b>\n"
    "/рецептзавтрак · /рецептобед · /рецептужин · /рецептбыстрый\n"
    "/менюдень · /менюнеделя\n"
    "/изчего — что приготовить из того, что есть\n"
    "/поискблюда — поиск по названию\n"
    "/фильтрнизкокалорийное · /фильтрбелковое · /фильтрдешевое\n"
    "/список — выбранные блюда · /списокпокупок\n"
    "/избранное · /предпочтения рыба, молоко\n\n"
    "<b>По-английски (то же самое):</b>\n"
    "/breakfast /lunch /dinner /quick /today /week /fromfridge /mylist /cart /favorites\n"
    "/prefs молоко, орехи · /search · /filterlowcal /filterprotein /filtercheap"
)


async def post_init(application: Application) -> None:
    """Меню команд слева от ввода (в Telegram разрешены только латинские /команды)."""
    await application.bot.set_my_commands(
        [
            BotCommand("start", "Главное меню и клавиатура"),
            BotCommand("help", "Справка"),
            BotCommand("breakfast", "Рецепты на завтрак"),
            BotCommand("lunch", "Рецепты на обед"),
            BotCommand("dinner", "Рецепты на ужин"),
            BotCommand("quick", "Быстрые рецепты"),
            BotCommand("today", "Меню на день"),
            BotCommand("week", "Меню на неделю"),
            BotCommand("fromfridge", "Рецепт из продуктов"),
            BotCommand("mylist", "Мой список блюд"),
            BotCommand("cart", "Список покупок"),
            BotCommand("favorites", "Избранное"),
            BotCommand("prefs", "Исключить продукты: /prefs молоко, рыба"),
            BotCommand("search", "Поиск по названию блюда"),
            BotCommand("filterlowcal", "Фильтр: низкокалорийное"),
            BotCommand("filterprotein", "Фильтр: белковое"),
            BotCommand("filtercheap", "Фильтр: дешевое"),
        ]
    )


def default_user_record() -> Dict:
    return {
        "favorites": [],
        "selected_recipe_ids": [],
        "shopping_recipe_ids": [],
        "shopping_items": [],
        "preferences": {
            "exclude_ingredients": [],
        },
    }


def load_storage() -> Dict:
    if not DATA_FILE.exists():
        return {"users": {}}
    try:
        with DATA_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Не удалось прочитать data.json: %s", exc)
        return {"users": {}}


def save_storage(storage: Dict) -> None:
    with DATA_FILE.open("w", encoding="utf-8") as f:
        json.dump(storage, f, ensure_ascii=False, indent=2)


def get_user(storage: Dict, user_id: int) -> Dict:
    users = storage.setdefault("users", {})
    key = str(user_id)
    users.setdefault(key, default_user_record())
    user = users[key]
    user.setdefault("shopping_recipe_ids", [])
    user.setdefault("shopping_items", [])
    return user


def recipe_allowed(recipe: Dict, exclude_ingredients: List[str]) -> bool:
    """Исключает блюдо, если любой из запрещённых продуктов встречается в строке ингредиента."""
    if not exclude_ingredients:
        return True
    blocked = {b.lower().strip() for b in exclude_ingredients if b and str(b).strip()}
    if not blocked:
        return True
    for item in recipe["ingredients"]:
        line = item.lower()
        for b in blocked:
            if b in line:
                return False
    return True


def format_recipe(recipe_id: str) -> str:
    recipe = RECIPES[recipe_id]
    servings = recipe.get("servings", 2)
    ingredients = "\n".join(f"- {item}" for item in recipe.get("ingredients", []))
    steps = "\n".join(
        f"{idx + 1}) {step}" for idx, step in enumerate(recipe.get("steps", []))
    )
    nutrition = recipe.get("nutrition", {})
    kcal = nutrition.get("kcal", "—")
    protein = nutrition.get("protein", "—")
    fat = nutrition.get("fat", "—")
    carbs = nutrition.get("carbs", "—")
    lines = [
        f"🍽 {recipe['name']}",
        f"⏱ ~{recipe['time']} мин · 👥 ~{servings} порц.",
        f"📊 КБЖУ на порцию: {kcal} ккал · Б {protein} г · Ж {fat} г · У {carbs} г",
        "",
        "Ингредиенты:",
        ingredients,
        "",
        "Шаги:",
        steps,
    ]
    tips = recipe.get("tips")
    if tips:
        lines.extend(["", f"💡 Совет: {tips}"])
    return "\n".join(lines)


def count_ingredient_overlap(user_ingredients: Set[str], recipe_ingredient_lines: List[str]) -> int:
    """Сколько строк ингредиентов «пересекается» с продуктами пользователя (подстрока)."""
    hits = 0
    for line in recipe_ingredient_lines:
        low = line.lower()
        if any(u in low for u in user_ingredients):
            hits += 1
    return hits


def is_cheap_recipe(recipe: Dict) -> bool:
    """Грубая оценка «дешевого» рецепта по составу ингредиентов."""
    ingredients = [str(x).lower() for x in recipe.get("ingredients", [])]
    expensive_hits = sum(
        1 for line in ingredients if any(keyword in line for keyword in EXPENSIVE_KEYWORDS)
    )
    return expensive_hits <= 1 and len(ingredients) <= 8


def recipe_matches_filter(recipe: Dict, filter_key: str) -> bool:
    nutrition = recipe.get("nutrition", {})
    kcal = nutrition.get("kcal")
    protein = nutrition.get("protein")

    if filter_key == "lowcal":
        return isinstance(kcal, (int, float)) and kcal <= LOW_KCAL_MAX
    if filter_key == "protein":
        return isinstance(protein, (int, float)) and protein >= HIGH_PROTEIN_MIN
    if filter_key == "cheap":
        return is_cheap_recipe(recipe)
    return False


def filter_title(filter_key: str) -> str:
    labels = {
        "lowcal": "низкокалорийные",
        "protein": "белковые",
        "cheap": "дешевые",
    }
    return labels.get(filter_key, filter_key)


def trim_label(text: str, max_len: int = 32) -> str:
    """Ограничивает длину текста для компактных inline-кнопок."""
    return text if len(text) <= max_len else text[: max_len - 1] + "…"


def rebuild_shopping_items(user: Dict) -> List[Dict]:
    """
    Пересобирает список покупок из выбранных рецептов.
    Сохраняет отметки «куплено» и пользовательские позиции.
    """
    grouped = Counter()
    for rid in user.get("shopping_recipe_ids", []):
        recipe = RECIPES.get(rid)
        if not recipe:
            continue
        grouped.update(ing.lower() for ing in recipe.get("ingredients", []))

    previous = user.get("shopping_items", [])
    previous_state = {
        str(item.get("name", "")).lower(): bool(item.get("bought", False))
        for item in previous
        if isinstance(item, dict) and item.get("name")
    }
    custom_items = [
        item
        for item in previous
        if isinstance(item, dict) and bool(item.get("custom")) and item.get("name")
    ]

    items: List[Dict] = []
    for name, count in sorted(grouped.items()):
        items.append(
            {
                "name": name,
                "count": int(count),
                "bought": previous_state.get(name, False),
                "custom": False,
            }
        )

    for item in custom_items:
        custom_name = str(item.get("name", "")).strip().lower()
        if not custom_name:
            continue
        items.append(
            {
                "name": custom_name,
                "count": int(item.get("count", 1) or 1),
                "bought": bool(item.get("bought", False)),
                "custom": True,
            }
        )

    user["shopping_items"] = items
    return items


def shopping_keyboard(items: List[Dict]) -> InlineKeyboardMarkup:
    buttons: List[List[InlineKeyboardButton]] = []
    for idx, item in enumerate(items):
        mark = "✅" if item.get("bought") else "⬜️"
        caption = f"{mark} {trim_label(str(item.get('name', '')))}"
        buttons.append([InlineKeyboardButton(caption, callback_data=f"shoptoggle|{idx}")])

    buttons.append([InlineKeyboardButton("➕ Добавить свою позицию", callback_data="shopcustom|add")])
    buttons.append([InlineKeyboardButton("🔄 Обновить список покупок", callback_data="shoprefresh")])
    return InlineKeyboardMarkup(buttons)


def parse_custom_item(text: str) -> Optional[Dict]:
    """
    Разбирает пользовательскую позицию покупок.
    Формат: 'молоко' или 'молоко x2'.
    """
    cleaned = text.strip().lower()
    if not cleaned:
        return None
    match = re.match(r"^(.*?)(?:\s*x\s*(\d+))?$", cleaned)
    if not match:
        return None
    name = (match.group(1) or "").strip()
    if not name:
        return None
    count = int(match.group(2) or 1)
    return {"name": name, "count": max(1, count), "bought": False, "custom": True}


def build_recipe_keyboard(
    recipe_ids: List[str], prefix: str, refresh_callback: Optional[str] = None
) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(RECIPES[rid]["name"], callback_data=f"{prefix}|{rid}")]
        for rid in recipe_ids
    ]
    if refresh_callback:
        buttons.append(
            [InlineKeyboardButton("🔄 Обновить список рецептов", callback_data=refresh_callback)]
        )
    return InlineKeyboardMarkup(buttons)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "Привет! Я помогу с простыми и вкусными рецептами 🍳\n\n"
        "<b>Удобный режим:</b> кнопки внизу экрана и быстрые инлайн-кнопки ниже.\n"
        "Полный список команд — кнопка «❓ Помощь» или меню <b>⌘</b> слева от поля ввода."
    )
    await update.message.reply_html(text, reply_markup=MAIN_KEYBOARD)
    await update.message.reply_html(
        "Ещё быстрее — нажми здесь:", reply_markup=main_menu_inline_keyboard()
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_html(HELP_TEXT, reply_markup=MAIN_KEYBOARD)


async def prefs_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Английская команда для предпочтений (видна в меню Telegram)."""
    if not context.args:
        await update.message.reply_text("Пример: /prefs молоко, рыба, орехи")
        return
    raw = " ".join(context.args)
    items = [x.strip().lower() for x in raw.split(",") if x.strip()]
    storage = load_storage()
    user = get_user(storage, update.effective_user.id)
    user["preferences"]["exclude_ingredients"] = items
    save_storage(storage)
    await update.message.reply_text("Сохранил предпочтения ✅")


async def set_preferences(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message_text = (update.message.text or "").strip()
    payload = message_text[len("/предпочтения") :].strip()
    if not payload:
        await update.message.reply_text(
            "Напишите так: /предпочтения рыба, молоко\n"
            "или англ. команду: /prefs milk, fish\n"
            "Я исключу эти продукты из предложений."
        )
        return

    items = [x.strip().lower() for x in payload.split(",") if x.strip()]
    storage = load_storage()
    user = get_user(storage, update.effective_user.id)
    user["preferences"]["exclude_ingredients"] = items
    save_storage(storage)
    await update.message.reply_text("Сохранил предпочтения ✅")


async def prompt_filter_menu(message) -> None:
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🥗 Низкокалорийное", callback_data="filter|lowcal")],
            [InlineKeyboardButton("💪 Белковое", callback_data="filter|protein")],
            [InlineKeyboardButton("💸 Дешевое", callback_data="filter|cheap")],
        ]
    )
    await message.reply_text("Выберите фильтр:", reply_markup=keyboard)


async def prompt_search_dish(message, context: ContextTypes.DEFAULT_TYPE) -> None:
    await message.reply_text("Введите название блюда для поиска.\nПример: омлет, паста, курица")
    context.user_data["awaiting_dish_query"] = True


async def show_filtered_recipe_list(
    message, context: ContextTypes.DEFAULT_TYPE, filter_key: str, user_id: int
) -> None:
    storage = load_storage()
    user = get_user(storage, user_id)
    excluded = user["preferences"]["exclude_ingredients"]
    filtered_ids = [
        rid
        for rid, recipe in RECIPES.items()
        if recipe_allowed(recipe, excluded) and recipe_matches_filter(recipe, filter_key)
    ]
    if not filtered_ids:
        await message.reply_text("По этому фильтру ничего не найдено. Попробуйте другой фильтр.")
        return

    shown = (
        sample(filtered_ids, min(MAX_RECIPES_IN_LIST, len(filtered_ids)))
        if len(filtered_ids) > MAX_RECIPES_IN_LIST
        else filtered_ids
    )
    list_title = f"Подходящие {filter_title(filter_key)} блюда:"
    set_pending_recipe_list(context, shown, list_title)
    context.user_data["last_filter_key"] = filter_key
    keyboard = build_recipe_keyboard(
        shown, "recipe", refresh_callback=f"refresh|filter:{filter_key}"
    )
    await message.reply_text(list_title, reply_markup=keyboard)


async def show_search_results(
    message, context: ContextTypes.DEFAULT_TYPE, query_text: str, user_id: int
) -> None:
    needle = query_text.strip().lower()
    if not needle:
        await message.reply_text("Пустой запрос. Введите название блюда.")
        return
    storage = load_storage()
    user = get_user(storage, user_id)
    excluded = user["preferences"]["exclude_ingredients"]
    matched = [
        rid
        for rid, recipe in RECIPES.items()
        if needle in recipe.get("name", "").lower() and recipe_allowed(recipe, excluded)
    ]
    if not matched:
        await message.reply_text("По названию ничего не найдено. Попробуйте другой запрос.")
        return
    shown = (
        sample(matched, min(MAX_RECIPES_IN_LIST, len(matched)))
        if len(matched) > MAX_RECIPES_IN_LIST
        else matched
    )
    list_title = f"Результаты поиска по запросу «{query_text}»:"
    set_pending_recipe_list(context, shown, list_title)
    context.user_data["last_search_query"] = query_text
    keyboard = build_recipe_keyboard(shown, "recipe", refresh_callback="refresh|search")
    await message.reply_text(list_title, reply_markup=keyboard)


async def search_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await prompt_search_dish(update.effective_message, context)


async def filter_lowcal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_filtered_recipe_list(update.effective_message, context, "lowcal", update.effective_user.id)


async def filter_protein(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_filtered_recipe_list(update.effective_message, context, "protein", update.effective_user.id)


async def filter_cheap(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_filtered_recipe_list(update.effective_message, context, "cheap", update.effective_user.id)


async def show_recipe_list(
    message, context: ContextTypes.DEFAULT_TYPE, mode: str, user_id: Optional[int] = None
) -> None:
    """Показать список рецептов (ответом на message)."""
    uid = user_id if user_id is not None else (message.from_user.id if message.from_user else None)
    if uid is None:
        return
    storage = load_storage()
    user = get_user(storage, uid)
    excluded = user["preferences"]["exclude_ingredients"]

    if mode == "quick":
        recipe_ids = [rid for rid, data in RECIPES.items() if data["quick"]]
    else:
        recipe_ids = [rid for rid, data in RECIPES.items() if data["meal"] == mode]

    recipe_ids = [rid for rid in recipe_ids if recipe_allowed(RECIPES[rid], excluded)]
    if not recipe_ids:
        await message.reply_text("Не нашел подходящих рецептов. Попробуйте изменить предпочтения.")
        return

    recipe_ids = (
        sample(recipe_ids, min(MAX_RECIPES_IN_LIST, len(recipe_ids)))
        if len(recipe_ids) > MAX_RECIPES_IN_LIST
        else recipe_ids
    )
    list_title = "Выберите блюдо из списка:"
    set_pending_recipe_list(context, recipe_ids, list_title)
    keyboard = build_recipe_keyboard(recipe_ids, "recipe", refresh_callback=f"refresh|{mode}")
    await message.reply_text(list_title, reply_markup=keyboard)


async def breakfast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_recipe_list(update.effective_message, context, "breakfast", update.effective_user.id)


async def lunch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_recipe_list(update.effective_message, context, "lunch", update.effective_user.id)


async def dinner(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_recipe_list(update.effective_message, context, "dinner", update.effective_user.id)


async def quick_recipe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_recipe_list(update.effective_message, context, "quick", update.effective_user.id)


def make_day_menu_options(filtered_recipe_ids: List[str]) -> List[List[str]]:
    breakfasts = [rid for rid in filtered_recipe_ids if RECIPES[rid]["meal"] == "breakfast"]
    lunches = [rid for rid in filtered_recipe_ids if RECIPES[rid]["meal"] == "lunch"]
    dinners = [rid for rid in filtered_recipe_ids if RECIPES[rid]["meal"] == "dinner"]
    variants = []
    for _ in range(3):
        if breakfasts and lunches and dinners:
            variants.append([sample(breakfasts, 1)[0], sample(lunches, 1)[0], sample(dinners, 1)[0]])
    return variants


async def send_menu_day(message, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = message.from_user.id if message.from_user else None
    if uid is None:
        return
    storage = load_storage()
    user = get_user(storage, uid)
    excluded = user["preferences"]["exclude_ingredients"]
    filtered = [rid for rid in RECIPES if recipe_allowed(RECIPES[rid], excluded)]
    variants = make_day_menu_options(filtered)
    if not variants:
        await message.reply_text("Не удалось собрать меню на день с текущими предпочтениями.")
        return

    context.user_data["day_menu_variants"] = variants
    buttons = []
    for idx, variant in enumerate(variants, start=1):
        labels = ", ".join(RECIPES[rid]["name"] for rid in variant)
        buttons.append([InlineKeyboardButton(f"Вариант {idx}: {labels}", callback_data=f"daymenu|{idx - 1}")])
    buttons.append([InlineKeyboardButton("🔄 Перегенерировать меню", callback_data="regenday")])
    await message.reply_text("Выберите вариант меню на день:", reply_markup=InlineKeyboardMarkup(buttons))


async def menu_day(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_menu_day(update.effective_message, context)


async def send_menu_week(message, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = message.from_user.id if message.from_user else None
    if uid is None:
        return
    storage = load_storage()
    user = get_user(storage, uid)
    excluded = user["preferences"]["exclude_ingredients"]
    filtered = [rid for rid in RECIPES if recipe_allowed(RECIPES[rid], excluded)]
    day_variants = make_day_menu_options(filtered)
    if not day_variants:
        await message.reply_text("Не удалось собрать меню на неделю с текущими предпочтениями.")
        return

    week = [sample(day_variants, 1)[0] for _ in range(7)]
    context.user_data["week_menu"] = week
    lines = []
    for day_idx, day_items in enumerate(week, start=1):
        lines.append(f"{day_idx} день: " + ", ".join(RECIPES[rid]["name"] for rid in day_items))
    await message.reply_text(
        "📅 Вариант меню на неделю:\n\n" + "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("🔄 Перегенерировать меню", callback_data="regenweek")]]
        ),
    )


async def menu_week(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_menu_week(update.effective_message, context)


async def send_list_selected(message, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
    storage = load_storage()
    user = get_user(storage, user_id)
    selected = user["selected_recipe_ids"]
    if not selected:
        await message.reply_text("Список пуст. Сначала выберите рецепты через меню.")
        return
    lines = [f"- {RECIPES[rid]['name']}" for rid in selected if rid in RECIPES]
    await message.reply_text("Вы выбрали:\n" + "\n".join(lines))


async def list_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_list_selected(update.effective_message, context, update.effective_user.id)


async def send_shopping_list(message, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
    storage = load_storage()
    user = get_user(storage, user_id)
    selected = [rid for rid in user.get("shopping_recipe_ids", []) if rid in RECIPES]
    if not selected and not user.get("shopping_items"):
        await message.reply_text(
            "Список покупок пуст. Откройте рецепт и нажмите «Добавить в покупки 🛒»."
        )
        return
    items = rebuild_shopping_items(user)
    save_storage(storage)
    if not items:
        await message.reply_text("Список покупок пока пуст.")
        return
    lines = [
        f"{'✅' if item.get('bought') else '⬜️'} {item['name']} x{item['count']}"
        for item in items
    ]
    await message.reply_text("🛒 Список покупок:\n" + "\n".join(lines), reply_markup=shopping_keyboard(items))


async def shopping_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_shopping_list(update.effective_message, context, update.effective_user.id)


async def prompt_from_fridge(message, context: ContextTypes.DEFAULT_TYPE) -> None:
    await message.reply_text(
        "Напишите продукты через запятую.\nПример: курица, рис, морковь"
    )
    context.user_data["awaiting_ingredients"] = True


async def from_what(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await prompt_from_fridge(update.effective_message, context)


async def show_from_ingredients_list(
    message, context: ContextTypes.DEFAULT_TYPE, user_ingredients: Set[str]
) -> None:
    """Показывает рецепты по введенным продуктам и дает кнопку обновления подборки."""
    scored = []
    for rid, recipe in RECIPES.items():
        ing = recipe["ingredients"]
        hits = count_ingredient_overlap(user_ingredients, ing)
        if hits > 0:
            ratio = hits / max(len(ing), 1)
            scored.append((hits, ratio, rid))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)

    top_pool = [rid for _, _, rid in scored]
    if not top_pool:
        await message.reply_text("Пока не нашел подходящих блюд из этих продуктов.")
        return

    top = (
        sample(top_pool, min(MAX_RECIPES_IN_LIST, len(top_pool)))
        if len(top_pool) > MAX_RECIPES_IN_LIST
        else top_pool
    )
    list_title = "Вот что можно приготовить:\nВыберите блюдо из списка:"
    set_pending_recipe_list(context, top, list_title)
    context.user_data["last_from_ingredients"] = sorted(user_ingredients)
    keyboard = build_recipe_keyboard(top, "recipe", refresh_callback="refresh|from")
    await message.reply_text(list_title, reply_markup=keyboard)


_MAIN_KB_ACTIONS = {
    "🌅 Завтрак": ("recipe", "breakfast"),
    "🍲 Обед": ("recipe", "lunch"),
    "🌙 Ужин": ("recipe", "dinner"),
    "⚡ Быстро": ("recipe", "quick"),
    "📆 Меню на день": ("day", None),
    "📅 Меню на неделю": ("week", None),
    "🥕 Из продуктов": ("from", None),
    "📋 Мой список": ("list", None),
    "🛒 Покупки": ("shop", None),
    "❤️ Избранное": ("favs", None),
    "❓ Помощь": ("help", None),
    "🧾 Фильтр": ("filter", None),
    "🔎 Поиск блюда": ("search", None),
}


async def free_text_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Кнопки главной клавиатуры + ввод продуктов для «Из продуктов»."""
    text = (update.message.text or "").strip()
    if context.user_data.get("awaiting_custom_shopping_item"):
        context.user_data["awaiting_custom_shopping_item"] = False
        parsed = parse_custom_item(text)
        if not parsed:
            await update.message.reply_text("Не понял формат. Пример: помидоры x2")
            return
        storage = load_storage()
        user = get_user(storage, update.effective_user.id)
        user.setdefault("shopping_items", []).append(parsed)
        save_storage(storage)
        await send_shopping_list(update.effective_message, context, update.effective_user.id)
        return

    if context.user_data.get("awaiting_dish_query"):
        context.user_data["awaiting_dish_query"] = False
        await show_search_results(update.message, context, text, update.effective_user.id)
        return

    if context.user_data.get("awaiting_ingredients"):
        user_ingredients = {item.strip().lower() for item in text.split(",") if item.strip()}
        context.user_data["awaiting_ingredients"] = False
        if not user_ingredients:
            await update.message.reply_text("Не увидел продукты. Попробуйте еще раз.")
            return
        await show_from_ingredients_list(update.message, context, user_ingredients)
        return

    act = _MAIN_KB_ACTIONS.get(text)
    if not act:
        return

    kind, mode = act
    if kind == "recipe" and mode is not None:
        await show_recipe_list(update.effective_message, context, mode, update.effective_user.id)
    elif kind == "day":
        await send_menu_day(update.effective_message, context)
    elif kind == "week":
        await send_menu_week(update.effective_message, context)
    elif kind == "from":
        await prompt_from_fridge(update.effective_message, context)
    elif kind == "list":
        await send_list_selected(update.effective_message, context, update.effective_user.id)
    elif kind == "shop":
        await send_shopping_list(update.effective_message, context, update.effective_user.id)
    elif kind == "favs":
        await send_favorites(update.effective_message, context, update.effective_user.id)
    elif kind == "help":
        await help_cmd(update, context)
    elif kind == "filter":
        await prompt_filter_menu(update.effective_message)
    elif kind == "search":
        await prompt_search_dish(update.effective_message, context)


async def send_favorites(message, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
    storage = load_storage()
    user = get_user(storage, user_id)
    favorites = [rid for rid in user["favorites"] if rid in RECIPES]
    if not favorites:
        await message.reply_text("Избранное пока пусто.")
        return
    lines = [f"- {RECIPES[rid]['name']}" for rid in favorites]
    await message.reply_text("❤️ Избранное:\n" + "\n".join(lines))


async def show_favorites(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_favorites(update.effective_message, context, update.effective_user.id)


async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    data = query.data or ""
    msg = query.message
    cq_user = query.from_user
    cq_uid = cq_user.id if cq_user else None

    if data.startswith("nav|") and msg and cq_uid is not None:
        action = data.split("|", 1)[1]
        await query.answer()
        if action == "breakfast":
            await show_recipe_list(msg, context, "breakfast", cq_uid)
        elif action == "lunch":
            await show_recipe_list(msg, context, "lunch", cq_uid)
        elif action == "dinner":
            await show_recipe_list(msg, context, "dinner", cq_uid)
        elif action == "quick":
            await show_recipe_list(msg, context, "quick", cq_uid)
        elif action == "day":
            await send_menu_day(msg, context)
        elif action == "week":
            await send_menu_week(msg, context)
        elif action == "from":
            await prompt_from_fridge(msg, context)
        elif action == "list":
            await send_list_selected(msg, context, cq_uid)
        elif action == "shop":
            await send_shopping_list(msg, context, cq_uid)
        elif action == "favs":
            await send_favorites(msg, context, cq_uid)
        elif action == "help":
            await msg.reply_html(HELP_TEXT, reply_markup=MAIN_KEYBOARD)
        elif action == "filter":
            await prompt_filter_menu(msg)
        elif action == "search":
            await prompt_search_dish(msg, context)
        return

    storage = load_storage()
    user = get_user(storage, cq_uid) if cq_uid is not None else None
    if user is None:
        await query.answer("Ошибка: нет данных пользователя", show_alert=False)
        return

    if data.startswith("recipe|"):
        await query.answer()
        rid = data.split("|", 1)[1]
        if rid not in RECIPES:
            await query.edit_message_text("Рецепт не найден.")
            return

        # Просмотр рецепта не должен автоматически попадать в покупки.
        if rid not in user["selected_recipe_ids"]:
            user["selected_recipe_ids"].append(rid)
        save_storage(storage)

        await query.edit_message_text(format_recipe(rid), reply_markup=recipe_action_keyboard(rid))
        return

    if data == "recipeback":
        await query.answer()
        pending = get_pending_recipe_list(context)
        if not pending or not pending.get("ids"):
            await query.edit_message_text("Список устарел. Откройте рецепты командой ещё раз.")
            return
        recipe_ids = [rid for rid in pending["ids"] if rid in RECIPES]
        if not recipe_ids:
            await query.edit_message_text("Рецепты из списка больше недоступны. Запросите список снова.")
            return
        title = pending.get("title") or "Выберите блюдо из списка:"
        keyboard = build_recipe_keyboard(recipe_ids, "recipe")
        await query.edit_message_text(title, reply_markup=keyboard)
        return

    if data.startswith("fav|"):
        rid = data.split("|", 1)[1]
        if rid in RECIPES and rid not in user["favorites"]:
            user["favorites"].append(rid)
            save_storage(storage)
            await query.answer("Добавлено в избранное ✅")
        else:
            await query.answer("Уже в избранном")
        return

    if data.startswith("shopadd|"):
        rid = data.split("|", 1)[1]
        shopping_ids = user.setdefault("shopping_recipe_ids", [])
        if rid in RECIPES and rid not in shopping_ids:
            shopping_ids.append(rid)
            save_storage(storage)
            await query.answer("Добавлено в список покупок ✅")
        else:
            await query.answer("Уже в списке покупок")
        return

    if data.startswith("refresh|") and msg:
        await query.answer()
        refresh_mode = data.split("|", 1)[1]
        if refresh_mode in {"breakfast", "lunch", "dinner", "quick"}:
            await show_recipe_list(msg, context, refresh_mode, cq_uid)
            return
        if refresh_mode.startswith("filter:"):
            filter_key = refresh_mode.split(":", 1)[1]
            if filter_key in {"lowcal", "protein", "cheap"} and cq_uid is not None:
                await show_filtered_recipe_list(msg, context, filter_key, cq_uid)
                return
        if refresh_mode == "search":
            query_text = context.user_data.get("last_search_query")
            if not query_text or cq_uid is None:
                await msg.reply_text("Введите поиск заново через кнопку «🔎 Поиск блюда».")
                return
            await show_search_results(msg, context, query_text, cq_uid)
            return
        if refresh_mode == "from":
            items = context.user_data.get("last_from_ingredients", [])
            if not items:
                await msg.reply_text("Сначала введите продукты через кнопку «🥕 Из продуктов».")
                return
            await show_from_ingredients_list(msg, context, set(items))
            return

    if data.startswith("filter|") and msg:
        await query.answer()
        filter_key = data.split("|", 1)[1]
        if filter_key in {"lowcal", "protein", "cheap"} and cq_uid is not None:
            await show_filtered_recipe_list(msg, context, filter_key, cq_uid)
        else:
            await msg.reply_text("Неизвестный фильтр.")
        return

    if data == "regenday" and msg:
        await query.answer()
        await send_menu_day(msg, context)
        return

    if data == "regenweek" and msg:
        await query.answer()
        await send_menu_week(msg, context)
        return

    if data == "shoprefresh" and msg and cq_uid is not None:
        await query.answer()
        await send_shopping_list(msg, context, cq_uid)
        return

    if data == "shopcustom|add":
        await query.answer()
        context.user_data["awaiting_custom_shopping_item"] = True
        await query.message.reply_text("Напишите новую позицию, например: яблоки x3")
        return

    if data.startswith("shoptoggle|") and msg and cq_uid is not None:
        await query.answer()
        idx_raw = data.split("|", 1)[1]
        try:
            idx = int(idx_raw)
        except ValueError:
            await msg.reply_text("Не удалось обработать выбранную позицию.")
            return
        storage = load_storage()
        user = get_user(storage, cq_uid)
        items = rebuild_shopping_items(user)
        if idx < 0 or idx >= len(items):
            await msg.reply_text("Элемент списка устарел. Обновите список покупок.")
            return
        items[idx]["bought"] = not bool(items[idx].get("bought"))
        user["shopping_items"] = items
        save_storage(storage)
        lines = [
            f"{'✅' if item.get('bought') else '⬜️'} {item['name']} x{item['count']}"
            for item in items
        ]
        await query.edit_message_text(
            "🛒 Список покупок:\n" + "\n".join(lines),
            reply_markup=shopping_keyboard(items),
        )
        return

    if data.startswith("daymenu|"):
        await query.answer()
        idx = int(data.split("|", 1)[1])
        variants = context.user_data.get("day_menu_variants", [])
        if not variants or idx >= len(variants):
            await query.edit_message_text("Вариант меню устарел. Вызовите /менюдень еще раз.")
            return

        selected = variants[idx]
        for rid in selected:
            if rid not in user["selected_recipe_ids"]:
                user["selected_recipe_ids"].append(rid)
        save_storage(storage)

        text = "🍽 Рецепты выбранного меню:\n\n" + "\n\n".join(format_recipe(rid) for rid in selected)
        await query.edit_message_text(text[:3900])


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Ошибка во время обработки апдейта: %s", context.error)
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text(
            "Упс, что-то пошло не так. Попробуйте еще раз чуть позже 🙏"
        )

application.post_init = post_init

application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("help", help_cmd))
application.add_handler(CommandHandler("prefs", prefs_cmd))

application.add_handler(CommandHandler("breakfast", breakfast))
application.add_handler(CommandHandler("lunch", lunch))
application.add_handler(CommandHandler("dinner", dinner))
application.add_handler(CommandHandler("quick", quick_recipe))
application.add_handler(CommandHandler("today", menu_day))
application.add_handler(CommandHandler("week", menu_week))
application.add_handler(CommandHandler("fromfridge", from_what))
application.add_handler(CommandHandler("search", search_cmd))
application.add_handler(CommandHandler("filterlowcal", filter_lowcal))
application.add_handler(CommandHandler("filterprotein", filter_protein))
application.add_handler(CommandHandler("filtercheap", filter_cheap))
application.add_handler(CommandHandler("mylist", list_selected))
application.add_handler(CommandHandler("cart", shopping_list))
application.add_handler(CommandHandler("favorites", show_favorites))

# русские команды
application.add_handler(MessageHandler(filters.Regex(r"^/предпочтения(\s+.+)?$"), set_preferences))
application.add_handler(MessageHandler(filters.Regex(r"^/рецептзавтрак$"), breakfast))
application.add_handler(MessageHandler(filters.Regex(r"^/рецептобед$"), lunch))
application.add_handler(MessageHandler(filters.Regex(r"^/рецептужин$"), dinner))
application.add_handler(MessageHandler(filters.Regex(r"^/рецептбыстрый$"), quick_recipe))
application.add_handler(MessageHandler(filters.Regex(r"^/менюдень$"), menu_day))
application.add_handler(MessageHandler(filters.Regex(r"^/менюнеделя$"), menu_week))
application.add_handler(MessageHandler(filters.Regex(r"^/список$"), list_selected))
application.add_handler(MessageHandler(filters.Regex(r"^/изчего$"), from_what))
application.add_handler(MessageHandler(filters.Regex(r"^/поискблюда$"), search_cmd))
application.add_handler(
    MessageHandler(filters.Regex(r"^/фильтрнизкокалорийное$"), filter_lowcal)
)
application.add_handler(MessageHandler(filters.Regex(r"^/фильтрбелковое$"), filter_protein))
application.add_handler(MessageHandler(filters.Regex(r"^/фильтрдешевое$"), filter_cheap))
application.add_handler(MessageHandler(filters.Regex(r"^/списокпокупок$"), shopping_list))
application.add_handler(MessageHandler(filters.Regex(r"^/избранное$"), show_favorites))

application.add_handler(CallbackQueryHandler(callback_router))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, free_text_router))

application.add_error_handler(error_handler)

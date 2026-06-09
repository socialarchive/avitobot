import asyncio
import json
import logging
import re
from pathlib import Path

import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
)

# ─────────────────────────────────────────────
#  Настройки
# ─────────────────────────────────────────────
TOKEN = "8863643517:AAHtaeUqeJO5LyBS8Rm2Awyc0PbDxw-7sfo"

# Прокси ТОЛЬКО для Telegram — Авито ходит напрямую
TELEGRAM_PROXY = None

DATA_FILE = Path("data.json")
CHECK_INTERVAL = 6 * 60             # проверка каждые 6 минут

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

AVITO_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
}


# ─────────────────────────────────────────────
#  Работа с данными
# ─────────────────────────────────────────────
def load_data() -> dict:
    if DATA_FILE.exists():
        try:
            return json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_data(data: dict) -> None:
    DATA_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def get_user(data: dict, user_id: int) -> dict:
    key = str(user_id)
    if key not in data:
        data[key] = {"keywords": [], "seen": []}
    return data[key]


# ─────────────────────────────────────────────
#  Парсинг RSS
# ─────────────────────────────────────────────
def parse_rss(xml_text: str) -> list[dict]:
    results = []
    items = re.findall(r"<item>(.*?)</item>", xml_text, re.DOTALL)
    for item in items:
        def get_tag(tag):
            m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", item, re.DOTALL)
            if m:
                text = m.group(1).strip()
                text = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", text, flags=re.DOTALL)
                return text.strip()
            return ""

        title = get_tag("title")
        link  = get_tag("link")
        desc  = get_tag("description")
        guid  = get_tag("guid") or link

        price_match = re.search(r"(\d[\d\s]*)\s*(?:руб|₽)", desc)
        price = price_match.group(0).strip() if price_match else "Цена не указана"

        if title and link:
            results.append({"id": guid, "title": title, "price": price, "link": link})
    return results


AVITO_COOKIES = {
    "uuid": "ae8bd0dd-e860-4572-5529-558c982b0e91",
    "cookiesyncs": "000000000000000000000000884470f2b4561278b5c2ffe8a6f536e50291e5d02c9a78e625a01a55a92ab87414d611afe0b462bccb3f90d225e313b3314c587b5b095a0a41dc4c8a38f6fa1be50a29ed495250d68ec84f699fa3b91dd31b69f5f495b7264e048bbf5ea2aebae2dcef29bda9904678a65bd279c878036759dd19f470ddd656794c4fcc2368d8967c92224696f52c30849a2c54fa48f22bb0237c9771e3b0a7bf4c13e8bc6b4043f81bb63672b84914a97d0cab47b89b099111d8003218ef2515b1c5a00c27ed1a53f0e0169ff426945bc514633deb6466f7cf6debf062df1f73620e022c9a8b58f0cd834692ab0596fc0e03316d799a51542074a3b249f2637caeea6de9e9981ae9a13e7fdb397aaa47b3cb71139142ba4fcbc3fc47a1abd76c85228fb25cf327fdbd3861b337854764f8aa5ef62853b89bc52f40d4a19db36509614b3ca57f29e8ee79057c10c71ecd5a5b959c285222f9290e98a1678ad399e72caae2bbdf2cf31a96ac7c133c083df744e24c9e0175988430f8116f1ba20562b7715355a57d386247fc4f72a6f9cf97bb53f287bf5e66f30d8efaba40e545df4226c583cf3cf56cb7f0025a3122b4566ff7d60c395f4633760f858f8fad5caff708214cc0e0dd8b464371e905a537aa6eae0e63e7ccb044fdc7f5224475d2eda006a1ebeeba740d9fe3570c949ab3c39f107deb21a01ba35fae1bcba87aaca417b301e4bc95be7b309ad6ac422571851382657f0dbaa4c2478706d0a7de3b5dee34db32f11fa6fa90fb08ae4ae7dfde4ef8c793e1c0e52dae4fe8faf53d07a573c107b61da204e182332eebe7fc81b355a36e37329f5b93e1a3d77a4d2bdbe24f480fb33ede3ae4b2d0ce57dcd5886cd9802b537937815edffd0eadf98c0bed5af98d2eb21eaa1cae69cbd2a2e777e3bea36bc3a8f8c83eaec693644b8f88f9d03adcb4be01b76695653799e39311a5e29c51522500355d60d576d409d38838d06429888a5c4e5be3fb7465dbde3a490b325cbf1a323ff6c5258c49b0f39e4b280056c9ce4d7abe451220fb1c5ed25b51efce21d78f6a6c615a9f9a06a99da8baeb7b2e87cfb775e7c590d11680ee5fe980660d63e4b338dfe7c773",
}


async def fetch_avito(keyword: str) -> list[dict]:
    """Парсим обычную страницу поиска Авито (без RSS)."""
    import random, json as _json
    url = (
        "https://www.avito.ru/rossiya?q="
        + keyword.replace(" ", "+")
        + "&s=104"
    )
    await asyncio.sleep(random.uniform(2.0, 5.0))
    try:
        async with httpx.AsyncClient(
            headers=AVITO_HEADERS,
            cookies=AVITO_COOKIES,
            follow_redirects=True,
            timeout=30,
            proxies=None,
        ) as client:
            resp = await client.get(url)
            if resp.status_code == 403:
                log.warning("Авито вернул 403 для '%s'", keyword)
                return []
            resp.raise_for_status()
            html = resp.text

            # Вытаскиваем данные из JSON внутри страницы
            m = re.search(r'"items"\s*:\s*\{"count".*?"items"\s*:\s*(\[.*?\])\s*,\s*"page"', html, re.DOTALL)
            if not m:
                # Fallback: парсим HTML напрямую
                results = []
                items = re.findall(
                    r'data-marker="item".*?href="(/[^"]+)".*?data-marker="item-title"[^>]*title="([^"]+)"',
                    html, re.DOTALL
                )
                for path, title in items[:20]:
                    link = "https://www.avito.ru" + path
                    guid = path
                    results.append({"id": guid, "title": title, "price": "Цена не указана", "link": link})
                return results

            try:
                items_data = _json.loads(m.group(1))
                results = []
                for item in items_data[:20]:
                    title = item.get("title", "")
                    link = "https://www.avito.ru" + item.get("urlPath", "")
                    price = item.get("priceDetailed", {}).get("string", "Цена не указана")
                    guid = str(item.get("id", link))
                    if title:
                        results.append({"id": guid, "title": title, "price": price, "link": link})
                return results
            except Exception:
                return []
    except Exception as e:
        log.warning("Ошибка при запросе к Авито (%s): %s", keyword, e)
        return []


# ─────────────────────────────────────────────
#  Команды бота
# ─────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "👋 Привет! Я слежу за новыми объявлениями на Авито и присылаю уведомления.\n\n"
        "📌 *Команды:*\n"
        "/add <слово> — добавить ключевое слово\n"
        "/list — мои ключевые слова\n"
        "/remove — удалить ключевое слово\n"
        "/check — проверить прямо сейчас\n"
        "/help — помощь\n\n"
        "Пример: `/add iPhone 14`"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_start(update, ctx)


async def cmd_add(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not ctx.args:
        await update.message.reply_text(
            "❗ Укажи ключевое слово. Пример: `/add велосипед`",
            parse_mode="Markdown",
        )
        return

    keyword = " ".join(ctx.args).strip()
    data = load_data()
    user = get_user(data, update.effective_user.id)

    if keyword.lower() in [k.lower() for k in user["keywords"]]:
        await update.message.reply_text(
            f"⚠️ Слово *{keyword}* уже есть в списке.", parse_mode="Markdown"
        )
        return

    if len(user["keywords"]) >= 20:
        await update.message.reply_text("❗ Максимум 20 ключевых слов.")
        return

    user["keywords"].append(keyword)
    save_data(data)
    await update.message.reply_text(
        f"✅ Добавил: *{keyword}*\nБуду проверять каждые 6 минут и присылать новые объявления.",
        parse_mode="Markdown",
    )


async def cmd_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    data = load_data()
    user = get_user(data, update.effective_user.id)

    if not user["keywords"]:
        await update.message.reply_text("📭 Список пуст. Добавь слова командой /add")
        return

    lines = [f"  {i+1}. {kw}" for i, kw in enumerate(user["keywords"])]
    text = "📋 *Твои ключевые слова:*\n" + "\n".join(lines)
    text += "\n\nЧтобы удалить — /remove"
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_remove(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    data = load_data()
    user = get_user(data, update.effective_user.id)

    if not user["keywords"]:
        await update.message.reply_text("📭 Список пуст.")
        return

    buttons = [
        [InlineKeyboardButton(f"❌ {kw}", callback_data=f"remove:{kw}")]
        for kw in user["keywords"]
    ]
    markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text("Выбери слово для удаления:", reply_markup=markup)


async def cb_remove(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    _, keyword = query.data.split(":", 1)
    data = load_data()
    user = get_user(data, query.from_user.id)
    if keyword in user["keywords"]:
        user["keywords"].remove(keyword)
        save_data(data)
        await query.edit_message_text(f"🗑️ Удалил: *{keyword}*", parse_mode="Markdown")
    else:
        await query.edit_message_text("Слово уже удалено.")


async def cmd_check(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    data = load_data()
    user = get_user(data, update.effective_user.id)

    if not user["keywords"]:
        await update.message.reply_text("📭 Нет ключевых слов. Добавь через /add")
        return

    await update.message.reply_text("🔍 Проверяю Авито прямо сейчас...")
    sent = await check_user(update.effective_user.id, user, ctx.bot)

    if sent == 0:
        await update.message.reply_text("😴 Новых объявлений не найдено.")
    else:
        await update.message.reply_text(f"✅ Отправил {sent} новых объявлений.")

    save_data(data)


# ─────────────────────────────────────────────
#  Фоновая проверка
# ─────────────────────────────────────────────
async def check_user(user_id: int, user: dict, bot) -> int:
    sent = 0
    seen: set = set(user.get("seen", []))

    for keyword in user.get("keywords", []):
        items = await fetch_avito(keyword)
        for item in items:
            if item["id"] not in seen:
                seen.add(item["id"])
                text = (
                    f"🆕 *Новое объявление*\n"
                    f"🔑 Поиск: _{keyword}_\n\n"
                    f"📦 {item['title']}\n"
                    f"💰 {item['price']}\n"
                    f"🔗 [Открыть на Авито]({item['link']})"
                )
                try:
                    await bot.send_message(
                        chat_id=user_id,
                        text=text,
                        parse_mode="Markdown",
                        disable_web_page_preview=False,
                    )
                    sent += 1
                    await asyncio.sleep(0.5)
                except Exception as e:
                    log.warning("Не удалось отправить сообщение %s: %s", user_id, e)

    user["seen"] = list(seen)[-2000:]
    return sent


async def check_user_all(ctx) -> None:
    data = load_data()
    for user_id_str, user in data.items():
        if user.get("keywords"):
            try:
                await check_user(int(user_id_str), user, ctx.bot)
            except Exception as e:
                log.warning("Ошибка при проверке %s: %s", user_id_str, e)
    save_data(data)


# ─────────────────────────────────────────────
#  Запуск
# ─────────────────────────────────────────────
def main() -> None:
    builder = (
        Application.builder()
        .token(TOKEN)
        .proxy(None)
        .get_updates_proxy(None)
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .pool_timeout(30)
        .get_updates_connect_timeout(30)
        .get_updates_read_timeout(30)
        .get_updates_write_timeout(30)
        .get_updates_pool_timeout(30)
    )
    app = builder.build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("add", cmd_add))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("remove", cmd_remove))
    app.add_handler(CommandHandler("check", cmd_check))
    app.add_handler(CallbackQueryHandler(cb_remove, pattern=r"^remove:"))

    app.job_queue.run_repeating(
        lambda ctx: asyncio.create_task(check_user_all(ctx)),
        interval=CHECK_INTERVAL,
        first=60,
    )

    log.info("Бот запущен! Нажми Ctrl+C для остановки.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()

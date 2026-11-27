"""Пересылает в Telegram-группу посты с 🔴 и 🟢 из канала @qazavtojol."""
import html
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

CHANNEL = "qazavtojol"
PAGE_URL = f"https://t.me/s/{CHANNEL}"
STATE_FILE = Path("state.json")
TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]
MARKERS = ("🔴", "🟢")
ALMATY = timezone(timedelta(hours=5))


def http_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def tg(method, **params):
    data = urllib.parse.urlencode(params).encode()
    url = f"https://api.telegram.org/bot{TOKEN}/{method}"
    with urllib.request.urlopen(url, data=data, timeout=30) as r:
        return r.read()


def clean(fragment):
    fragment = re.sub(r"<br\s*/?>", "\n", fragment)
    fragment = re.sub(r"</(p|div)>", "\n", fragment)
    fragment = re.sub(r"<[^>]+>", "", fragment)
    text = html.unescape(fragment)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def parse_posts(page):
    marks = list(re.finditer(rf'data-post="{CHANNEL}/(\d+)"', page))
    posts = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(page)
        chunk = page[m.start():end]

        # сначала убираем блок «ответ на...», чтобы не перепутать текст
        reply_text = ""
        rm = re.search(
            r'tgme_widget_message_reply.*?tgme_widget_message_metatext[^>]*>(.*?)</div>',
            chunk, re.S)
        if rm:
            reply_text = clean(rm.group(1))
            chunk = chunk.replace(rm.group(0), "")

        tm = re.search(r'js-message_text[^>]*>(.*?)</div>\s*(?:<div class="tgme_widget|<span|</div>)',
                       chunk, re.S)
        if not tm:
            tm = re.search(r'js-message_text[^>]*>(.*?)</div>', chunk, re.S)
        text = clean(tm.group(1)) if tm else ""

        dm = re.search(r'<time[^>]*datetime="([^"]+)"', chunk)
        when = None
        if dm:
            try:
                when = datetime.fromisoformat(dm.group(1)).astimezone(ALMATY)
            except ValueError:
                pass

        pm = re.search(r"tgme_widget_message_photo_wrap[^>]*background-image:url\('([^']+)'\)", chunk)
        posts.append({
            "id": int(m.group(1)),
            "text": text,
            "reply": reply_text,
            "time": when,
            "photo": pm.group(1) if pm else None,
        })
    return posts


def send(post):
    emoji = next((e for e in MARKERS if e in post["text"]), "")
    when = post["time"].strftime("%d.%m.%Y %H:%M") if post["time"] else ""
    parts = [f"{emoji} {when} (Алматы)".strip(), "", post["text"]]
    if post["reply"] and "🟢" in post["text"]:
        parts += ["", "Ответ на: " + post["reply"][:300]]
    parts += ["", f"https://t.me/{CHANNEL}/{post['id']}"]
    message = "\n".join(parts)[:4000]

    if post["photo"]:
        try:
            tg("sendPhoto", chat_id=CHAT_ID, photo=post["photo"])
        except Exception as e:
            print("Фото не отправилось:", e)
    tg("sendMessage", chat_id=CHAT_ID, text=message, disable_web_page_preview="true")


def main():
    posts = parse_posts(http_get(PAGE_URL))
    if not posts:
        print("Посты не найдены (возможно, изменилась вёрстка страницы)")
        return
    newest = max(p["id"] for p in posts)

    if STATE_FILE.exists():
        last_id = json.loads(STATE_FILE.read_text())["last_id"]
    else:
        # первый запуск: ничего не отправляем, просто запоминаем, где мы
        STATE_FILE.write_text(json.dumps({"last_id": newest}))
        print("Первый запуск, запомнили пост", newest)
        return

    for p in sorted(posts, key=lambda x: x["id"]):
        if p["id"] > last_id and any(e in p["text"] for e in MARKERS):
            send(p)
            print("Отправлен пост", p["id"])

    STATE_FILE.write_text(json.dumps({"last_id": max(last_id, newest)}))


main()

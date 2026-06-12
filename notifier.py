import hashlib
import html
import json
import os
import requests

import feedback as fb

TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
API_BASE = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

_MY = {
    "budget":     "600-1300 zł",
    "color":      "тёмный",
    "handlebar":  "прямой руль",
    "posture":    "прямая",
    "frame_size": "M 17-18\"",
    "wheels":     "28\" 700c",
    "tires":      "38-45 мм",
    "gears":      "Altus/Acera",
    "brakes":     "V-brake/диск",
    "suspension": "без",
}

_LABELS = {
    "budget":     "Бюджет",
    "color":      "Цвет",
    "handlebar":  "Уровень руля",
    "posture":    "Посадка",
    "frame_size": "Рама",
    "wheels":     "Колёса",
    "tires":      "Покрышки",
    "gears":      "Передачи",
    "brakes":     "Тормоза",
    "suspension": "Амортизатор",
}


def _listing_id(link: str) -> str:
    return hashlib.md5(link.encode()).hexdigest()[:8]


def _build_message(listing: dict, result: dict) -> str:
    verdict = result.get("verdict", "ВОЗМОЖНО")
    verdict_emoji = {"ДА": "✅", "ВОЗМОЖНО": "🤔"}.get(verdict, "🤔")
    priority = result.get("priority_model", False)
    model_name = result.get("model_name")
    params = result.get("params", {})

    lines = [f"{verdict_emoji} <b>{html.escape(listing.get('title', '—'))}</b> | {html.escape(listing.get('price', '—'))}"]

    if model_name:
        if priority:
            lines.append(f"⭐ <b>{html.escape(model_name)}</b> — приоритетная модель")
        else:
            lines.append(f"— <b>{html.escape(model_name)}</b> — не в приоритете")

    lines.append("")

    comments = []
    for key, label in _LABELS.items():
        p = params.get(key, {})
        match = p.get("match", "❓")
        value = html.escape(p.get("value", "—"), quote=False)
        my = html.escape(_MY.get(key, ""), quote=False)
        comment = p.get("comment", "")

        lines.append(f"{match} <b>{label}</b> [{my}] = {value}")

        if comment:
            comments.append(f"• {label}: {html.escape(comment, quote=False)}")

    for bonus in result.get("bonuses", []):
        comments.append(f"➕ {html.escape(bonus, quote=False)}")
    for defect in result.get("defects", []):
        comments.append(f"⚠️ {html.escape(defect, quote=False)}")

    if comments:
        lines.append("")
        lines.append("На что обратить внимание:")
        lines.extend(comments)

    lines.append("")
    lines.append(f'<a href="{html.escape(listing.get("link", ""), quote=False)}">🔗 Смотреть на OLX</a>')

    return "\n".join(lines)


def send_listing(listing: dict, result: dict) -> None:
    text = _build_message(listing, result)
    lid = _listing_id(listing.get("link", ""))
    photo_url = (listing.get("photos") or [None])[0]

    markup = {
        "inline_keyboard": [[
            {"text": "✅ Подходит", "callback_data": f"yes:{lid}"},
            {"text": "❌ Не подходит", "callback_data": f"no:{lid}"},
        ]]
    }

    if photo_url:
        _send_photo(photo_url, text, markup)
    else:
        _send_message(text, markup)

    fb.save_pending(lid, listing, result)


def _send_photo(photo_url: str, caption: str, markup: dict) -> None:
    if len(caption) > 1024:
        requests.post(
            f"{API_BASE}/sendPhoto",
            data={"chat_id": TELEGRAM_CHAT_ID, "photo": photo_url},
            timeout=10,
        )
        _send_message(caption, markup)
        return

    resp = requests.post(
        f"{API_BASE}/sendPhoto",
        data={
            "chat_id": TELEGRAM_CHAT_ID,
            "photo": photo_url,
            "caption": caption,
            "parse_mode": "HTML",
            "reply_markup": json.dumps(markup),
        },
        timeout=10,
    )
    if not resp.ok:
        _send_message(caption, markup)


def _send_message(text: str, markup: dict) -> None:
    requests.post(
        f"{API_BASE}/sendMessage",
        json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
            "reply_markup": markup,
        },
        timeout=10,
    )

import json
import os
import requests
from datetime import datetime

FEEDBACK_FILE = "feedback.json"
PENDING_FILE = "pending.json"
OFFSET_FILE = "telegram_offset.json"


def _api_base() -> str:
    return f"https://api.telegram.org/bot{os.getenv('TELEGRAM_BOT_TOKEN', '')}"


def _chat_id() -> str:
    return os.getenv("TELEGRAM_CHAT_ID", "")


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _save(path, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def save_pending(listing_id: str, listing: dict) -> None:
    pending = _load(PENDING_FILE, {})
    pending[listing_id] = {
        "link": listing.get("link", ""),
        "title": listing.get("title", ""),
        "price": listing.get("price", ""),
    }
    _save(PENDING_FILE, pending)


def collect_feedback() -> int:
    """Собирает нажатия кнопок и текстовые комментарии из Telegram. Возвращает кол-во новых."""
    offset = _load(OFFSET_FILE, {"offset": 0}).get("offset", 0)

    try:
        resp = requests.get(
            f"{_api_base()}/getUpdates",
            params={"offset": offset, "timeout": 3},
            timeout=10,
        )
        updates = resp.json().get("result", []) if resp.ok else []
    except Exception:
        return 0

    if not updates:
        return 0

    pending = _load(PENDING_FILE, {})
    feedback_list = _load(FEEDBACK_FILE, [])
    count = 0

    for update in updates:
        # Нажатие кнопки ДА / НЕТ
        if "callback_query" in update:
            cq = update["callback_query"]
            data = cq.get("data", "")

            if ":" in data:
                action, listing_id = data.split(":", 1)
                verdict = "ДА" if action == "yes" else "НЕТ"
                info = pending.get(listing_id, {})
                original_msg_id = cq.get("message", {}).get("message_id")

                feedback_list.append({
                    "link": info.get("link", ""),
                    "title": info.get("title", ""),
                    "verdict": verdict,
                    "comment": "",
                    "timestamp": datetime.now().isoformat(),
                })
                count += 1

                # Убираем кнопки с исходного сообщения
                if original_msg_id:
                    requests.post(
                        f"{_api_base()}/editMessageReplyMarkup",
                        json={"chat_id": _chat_id(), "message_id": original_msg_id, "reply_markup": {"inline_keyboard": []}},
                        timeout=5,
                    )

                # Отбивка в чат
                reply_text = "✅ Принято — подходит" if verdict == "ДА" else "❌ Принято — не подходит"
                requests.post(
                    f"{_api_base()}/sendMessage",
                    json={
                        "chat_id": _chat_id(),
                        "text": reply_text,
                        "reply_to_message_id": original_msg_id,
                    },
                    timeout=5,
                )

                requests.post(
                    f"{_api_base()}/answerCallbackQuery",
                    json={"callback_query_id": cq["id"]},
                    timeout=5,
                )

        # Текстовое сообщение — комментарий к последнему велосипеду
        elif "message" in update:
            msg = update["message"]
            if str(msg.get("chat", {}).get("id", "")) != str(_chat_id()):
                continue
            text = msg.get("text", "").strip()
            if not text or text.startswith("/"):
                continue

            if feedback_list:
                feedback_list[-1]["comment"] = text
                count += 1

    _save(OFFSET_FILE, {"offset": updates[-1]["update_id"] + 1})
    _save(FEEDBACK_FILE, feedback_list)

    return count


def get_feedback_examples() -> str:
    """Возвращает примеры из feedback для включения в промпт Claude."""
    feedback_list = _load(FEEDBACK_FILE, [])
    entries = [f for f in feedback_list if f.get("verdict") in ("ДА", "НЕТ")]
    if not entries:
        return ""

    lines = [
        "\nПримеры из обратной связи пользователя — используй для калибровки оценок:"
    ]
    for f in entries[-20:]:
        title = f.get("title", "")[:60]
        verdict = f.get("verdict", "")
        comment = f.get("comment", "")
        marker = "✓ ПОДОШЛО" if verdict == "ДА" else "✗ НЕ ПОДОШЛО"
        line = f"{marker}: {title}"
        if comment:
            line += f" — {comment}"
        lines.append(line)

    return "\n".join(lines)

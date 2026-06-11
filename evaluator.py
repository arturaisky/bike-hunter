import json
import re
from dotenv import load_dotenv
load_dotenv()

import anthropic
import feedback as fb

client = anthropic.Anthropic()

_FILTER_PROMPT = """Ты фильтр объявлений о велосипедах. Отвечай ТОЛЬКО одним словом: ДА или НЕТ.

НЕТ — если объявление явно не подходит хотя бы по одному из критериев:
- детский велосипед (слово dziecięcy/junior/dla dzieci и т.п.)
- чисто горный (MTB) с зубастой резиной и амортизационной вилкой
- шоссейный/гоночный велосипед (баранки, drop bar, szosowy)
- не велосипед вообще
- цена явно вне диапазона 400–1600 zł
- размер рамы явно указан и не подходит: нужен M (17–18", 44–46 см) — НЕТ если указано ≤15" или ≥20" (54 см+)
- размер колёс явно указан и не 28" / 700c — НЕТ если указано 24", 26" или 29"

ВАЖНО: если размер рамы или колёс не указан — отвечай ДА, не угадывай.

ДА — если это может быть кросс, трекинг, гибрид, гравийный или похожий велосипед для взрослого."""


def quick_filter(listing: dict) -> bool:
    """Быстрая проверка через Haiku. Возвращает False если объявление явно не подходит."""
    params_text = "\n".join(listing.get("params", [])) or "не указаны"
    description = (listing.get("description") or "")[:400]
    text = (
        f"Название: {listing.get('title', '—')}\n"
        f"Цена: {listing.get('price', '—')}\n"
        f"Параметры:\n{params_text}\n"
        f"Описание:\n{description}"
    )
    try:
        resp = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=10,
            system=_FILTER_PROMPT,
            messages=[{"role": "user", "content": text}],
        )
        return "ДА" in resp.content[0].text.strip().upper()
    except Exception:
        return True  # при ошибке — пропускаем на полную оценку


SYSTEM_PROMPT = """Ты — эксперт по велосипедам. Оцениваешь б/у велосипеды с OLX.pl для конкретного покупателя.

Критерии покупателя:
- Тип: гибрид / кросс / трекинг / фитнес-гибрид. НЕ горный (MTB), НЕ шоссейный/гоночный
- Бюджет: 600–1300 zł
- Цвет: тёмный. Идеально чёрный. Серый, коричневый — ОК. Яркие цвета — нежелательно
- Уровень руля: прямой руль (flat bar), руль на уровне седла или выше. Без баранок
- Посадка: прямая или умеренно прямая
- Рама: размер M (17–18", ~44–46 см). Рост покупателя 173 см
- Колёса: 28" / 700c
- Покрышки: 38–45 мм, не очень зубастые, не слики
- Передачи: Shimano Altus / Acera / Alivio (предпочтительно)
- Тормоза: V-brake или диски (не критично что именно)
- Амортизатор: без (с амортизатором — минус, но не отказ)

Приоритетные модели: Merida Crossway, Cube Nature, Kross Evado, Unibike Crossfire,
Trek FX, Giant Escape, Specialized Sirrus, Cannondale Quick, Trek Dual Sport, Giant Roam

Дилбрейкеры — если хотя бы один из этих параметров ❌, verdict = "НЕТ" без исключений:
- frame_size: рама явно не M (например, указано 15", 19", 21" или 54+ см)
- wheels: колёса явно не 28" / 700c (например, 26" или 29")
- handlebar: баранки / drop bar / шоссейный руль

Если параметр не указан в объявлении — ставь ❓, не ❌. Дилбрейкер срабатывает только при явном несоответствии.

Важно: продавцы часто пропускают характеристики или ставят не ту категорию.
Анализируй название, описание, параметры и фото вместе. Если знаешь модель — используй свои знания.

Верни ТОЛЬКО валидный JSON без какого-либо текста до или после него:

{
  "verdict": "ДА",
  "priority_model": false,
  "model_name": null,
  "params": {
    "budget":     {"value": "900 zł",        "match": "✅", "comment": ""},
    "color":      {"value": "чёрный",        "match": "✅", "comment": ""},
    "handlebar":  {"value": "прямой руль",   "match": "✅", "comment": ""},
    "posture":    {"value": "прямая",        "match": "✅", "comment": ""},
    "frame_size": {"value": "M / 17\"",      "match": "✅", "comment": ""},
    "wheels":     {"value": "28\" / 700c",   "match": "✅", "comment": ""},
    "tires":      {"value": "40 мм",         "match": "✅", "comment": ""},
    "gears":      {"value": "Shimano Acera", "match": "✅", "comment": ""},
    "brakes":     {"value": "V-brake",       "match": "✅", "comment": ""},
    "suspension": {"value": "нет",           "match": "✅", "comment": ""}
  },
  "bonuses": ["замок в комплекте", "запасная покрышка"],
  "defects": ["царапина на верхней трубе", "без педалей"]
}

bonuses — только то, что продавец явно упоминает в тексте как включённое в продажу ("sprzedam razem z...", "w zestawie", "w cenie" и т.п.). НЕ добавляй ничего на основании фотографий — наличие замка или фонарика на фото не означает, что они продаются вместе. Пустой список [], если в тексте ничего не сказано.
defects — дефекты, повреждения, отсутствующие детали, оговорённые минусы. Пустой список [], если не упомянуто.

Правила для match:
- "✅" — полностью соответствует критерию
- "⚠️" — частично / на грани (например, рама 19" вместо M)
- "❌" — не соответствует
- "❓" — не указано в объявлении, нужно уточнять

verdict — одно из: "ДА" / "НЕТ" / "ВОЗМОЖНО"
model_name — название модели если определена, иначе null
comment — краткий комментарий (1 предложение макс.), пустая строка если не нужен"""


def evaluate_listing(listing: dict) -> dict:
    """
    Оценивает объявление через Claude API.
    Возвращает структурированный dict с verdict, priority_model, model_name, params.
    """
    content = []

    for photo_url in listing.get("photos", [])[:3]:
        content.append({
            "type": "image",
            "source": {"type": "url", "url": photo_url},
        })

    params_text = "\n".join(listing.get("params", [])) or "не указаны"
    description = (listing.get("description") or "нет описания")[:1500]

    content.append({
        "type": "text",
        "text": (
            f"Название: {listing.get('title', '—')}\n"
            f"Цена: {listing.get('price', '—')}\n"
            f"Ссылка: {listing.get('link', '—')}\n\n"
            f"Параметры:\n{params_text}\n\n"
            f"Описание:\n{description}"
        ),
    })

    system_text = SYSTEM_PROMPT + fb.get_feedback_examples()

    response = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=2048,
        system=[{
            "type": "text",
            "text": system_text,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{"role": "user", "content": content}],
    )

    raw_text = next((b.text for b in response.content if b.type == "text"), "")

    try:
        # Убираем markdown-обёртку если Claude всё же добавил ```json
        clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_text.strip())
        data = json.loads(clean)
    except (json.JSONDecodeError, ValueError):
        # Ищем JSON внутри текста
        match = re.search(r"\{.*\}", raw_text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                data = _fallback(raw_text)
        else:
            data = _fallback(raw_text)

    return data


def _fallback(raw_text: str) -> dict:
    """Если JSON не распарсился — вернуть минимальный результат."""
    verdict = "ВОЗМОЖНО"
    if "НЕТ" in raw_text:
        verdict = "НЕТ"
    elif "ДА" in raw_text:
        verdict = "ДА"
    return {
        "verdict": verdict,
        "priority_model": False,
        "model_name": None,
        "params": {},
        "_raw": raw_text,
    }


if __name__ == "__main__":
    import json as _json
    test = {
        "title": "Merida Crossway 20 rozmiar M",
        "price": "900 zł",
        "link": "https://www.olx.pl/test",
        "description": "Sprzedaję rower Merida Crossway 20, rozmiar M, koła 28 cali, przerzutki Shimano Acera, stan dobry, kolor czarny.",
        "params": ["Rozmiar ramy: M", "Rozmiar kół: 28\"", "Kolor: czarny"],
        "photos": [],
    }
    result = evaluate_listing(test)
    print(_json.dumps(result, ensure_ascii=False, indent=2))

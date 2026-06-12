import json
import os
from dotenv import load_dotenv
load_dotenv()

import gspread

SPREADSHEET_ID = "10laWl7vcXq7ToK0Jul_fce6cHwMNaY65IdX1dAYaABY"
FEEDBACK_FILE = "feedback.json"
CREDS_FILE = "google_credentials.json"

PARAM_ORDER = [
    ("frame_size", "Рама"),
    ("wheels",     "Колёса"),
    ("handlebar",  "Руль"),
    ("gears",      "Передачи"),
    ("brakes",     "Тормоза"),
    ("color",      "Цвет"),
    ("tires",      "Покрышки"),
    ("posture",    "Посадка"),
    ("budget",     "Бюджет"),
    ("suspension", "Амортизатор"),
]

HEADERS = (
    ["Дата", "Название", "Цена", "Источник", "Ссылка", "Фото"]
    + [label for _, label in PARAM_ORDER]
    + ["Бонусы", "Дефекты", "Комментарий"]
)


def _param_cell(params: dict, key: str) -> str:
    p = params.get(key, {})
    match = p.get("match", "❓")
    value = p.get("value", "—")
    comment = p.get("comment", "")
    cell = f"{match} {value}"
    if comment:
        cell += f"\n({comment})"
    return cell


def sync():
    if not os.path.exists(CREDS_FILE):
        print(f"Файл {CREDS_FILE} не найден — пропускаем синхронизацию с Google Sheets")
        return

    try:
        gc = gspread.service_account(filename=CREDS_FILE)
    except Exception as e:
        print(f"Ошибка авторизации Google Sheets: {e}")
        return

    try:
        sh = gc.open_by_key(SPREADSHEET_ID)
        ws = sh.sheet1
    except Exception as e:
        print(f"Ошибка открытия таблицы: {e}")
        return

    try:
        with open(FEEDBACK_FILE, encoding="utf-8") as f:
            feedback_list = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        feedback_list = []

    approved = [e for e in feedback_list if e.get("verdict") == "ДА"]
    if not approved:
        print("Нет одобренных объявлений для синхронизации.")
        return

    rows = [HEADERS]
    for entry in approved:
        result = entry.get("result", {})
        params = result.get("params", {})

        date = (entry.get("timestamp") or "")[:10]
        title = entry.get("title", "—")
        price = entry.get("price", "—")
        source = entry.get("source", "—")
        link = entry.get("link", "")
        photo = entry.get("photo", "")

        photo_cell = f'=IMAGE("{photo}")' if photo else ""
        param_cells = [_param_cell(params, key) for key, _ in PARAM_ORDER]
        bonuses = "; ".join(result.get("bonuses", []))
        defects = "; ".join(result.get("defects", []))
        comment = entry.get("comment", "")

        rows.append([date, title, price, source, link, photo_cell] + param_cells + [bonuses, defects, comment])

    ws.clear()
    ws.append_rows(rows, value_input_option="USER_ENTERED")

    ws.format("A1:T1", {
        "textFormat": {"bold": True},
        "backgroundColor": {"red": 0.17, "green": 0.36, "blue": 0.63},
    })

    print(f"Таблица обновлена: {len(approved)} велосипедов → Google Sheets")


if __name__ == "__main__":
    sync()

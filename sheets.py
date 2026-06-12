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
    ["Дата", "Название", "Цена", "Модель", "Источник", "Ссылка", "Фото"]
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


def _build_entry_data(entry: dict) -> dict:
    """Возвращает dict {название_столбца: значение} для одной записи."""
    result = entry.get("result", {})
    params = result.get("params", {})
    photo = entry.get("photo", "")
    model_name = result.get("model_name") or ""
    priority = result.get("priority_model", False)

    data = {
        "Дата":       (entry.get("timestamp") or "")[:10],
        "Название":   entry.get("title", "—"),
        "Цена":       entry.get("price", "—"),
        "Модель":     ("⭐ " if priority else "— ") + model_name if model_name else "",
        "Источник":   entry.get("source", "—"),
        "Ссылка":     entry.get("link", ""),
        "Фото":       f'=IMAGE("{photo}")' if photo else "",
        "Бонусы":     "; ".join(result.get("bonuses", [])),
        "Дефекты":    "; ".join(result.get("defects", [])),
        "Комментарий": entry.get("comment", ""),
    }
    for key, label in PARAM_ORDER:
        data[label] = _param_cell(params, key)
    return data


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

    # Читаем заголовки из таблицы
    existing_headers = ws.row_values(1)

    if not existing_headers:
        # Первый запуск — пишем заголовки
        ws.append_row(HEADERS, value_input_option="USER_ENTERED")
        ws.format("A1:U1", {
            "textFormat": {"bold": True},
            "backgroundColor": {"red": 0.17, "green": 0.36, "blue": 0.63},
        })
        existing_headers = HEADERS

    # Карта: название столбца → индекс (0-based)
    col_index = {name: i for i, name in enumerate(existing_headers)}
    n_cols = len(existing_headers)

    # Ссылки уже в таблице — чтобы не дублировать
    link_col = col_index.get("Ссылка")
    existing_links = set()
    if link_col is not None:
        all_rows = ws.get_all_values()
        existing_links = {
            row[link_col] for row in all_rows[1:]
            if len(row) > link_col and row[link_col]
        }

    new_entries = [e for e in approved if e.get("link") not in existing_links]
    if not new_entries:
        print("Нет новых одобренных объявлений для добавления.")
        return

    new_rows = []
    for entry in new_entries:
        row = [""] * n_cols
        for col_name, value in _build_entry_data(entry).items():
            if col_name in col_index:
                row[col_index[col_name]] = value
        new_rows.append(row)

    ws.append_rows(new_rows, value_input_option="USER_ENTERED")
    print(f"Добавлено в таблицу: {len(new_rows)} велосипедов")


if __name__ == "__main__":
    sync()

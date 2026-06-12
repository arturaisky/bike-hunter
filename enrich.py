"""
Дообогащает одобренные записи в feedback.json, у которых нет данных Claude
(были одобрены до того как мы начали сохранять полный результат).
"""
import json
import time
from dotenv import load_dotenv
load_dotenv()

import scraper
import evaluator
import sheets

FEEDBACK_FILE = "feedback.json"


def _needs_enrichment(entry: dict) -> bool:
    if entry.get("verdict") != "ДА":
        return False
    result = entry.get("result", {})
    return not result.get("params")


def enrich():
    try:
        with open(FEEDBACK_FILE, encoding="utf-8") as f:
            feedback_list = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print("feedback.json не найден")
        return

    to_enrich = [e for e in feedback_list if _needs_enrichment(e)]
    print(f"Записей для обогащения: {len(to_enrich)}")

    if not to_enrich:
        print("Все одобренные записи уже имеют данные.")
        return

    updated = 0
    for i, entry in enumerate(to_enrich, 1):
        link = entry.get("link", "")
        title = entry.get("title", "")[:60]
        print(f"[{i}/{len(to_enrich)}] {title}")

        if not link:
            print("  → нет ссылки, пропуск")
            continue

        try:
            details = scraper.scrape_listing_details(link)
        except Exception as e:
            print(f"  → ошибка скрапинга: {e}")
            continue

        # Если название не известно — берём из страницы объявления
        title_known = entry.get("title", "")
        if not title_known:
            try:
                import requests
                from bs4 import BeautifulSoup
                resp = requests.get(link, headers=scraper.HEADERS, timeout=15)
                soup = BeautifulSoup(resp.text, "html.parser")
                h = soup.find("h4") or soup.find("h1")
                if h:
                    title_known = h.get_text(strip=True)
                price_tag = soup.find("div", class_="css-90xrc0") or soup.find("p", attrs={"data-testid": "ad-price"})
                price_known = price_tag.get_text(strip=True) if price_tag else entry.get("price", "")
            except Exception:
                price_known = entry.get("price", "")
        else:
            price_known = entry.get("price", "")

        listing = {
            "link": link,
            "title": title_known,
            "price": price_known,
            "source": entry.get("source", ""),
            **details,
        }

        try:
            result = evaluator.evaluate_listing(listing)
        except Exception as e:
            print(f"  → ошибка Claude: {e}")
            continue

        # Обновляем запись в feedback_list
        for fb_entry in feedback_list:
            if fb_entry.get("link") == link and not fb_entry.get("result", {}).get("params"):
                fb_entry["result"] = result
                fb_entry["title"] = fb_entry.get("title") or title_known
                fb_entry["price"] = fb_entry.get("price") or price_known
                fb_entry["photo"] = (details.get("photos") or [None])[0] or ""
                fb_entry["source"] = fb_entry.get("source") or listing.get("source", "")
                break

        verdict = result.get("verdict", "?")
        model = result.get("model_name") or ""
        print(f"  → {verdict} {model}")
        updated += 1
        time.sleep(1)

    with open(FEEDBACK_FILE, "w", encoding="utf-8") as f:
        json.dump(feedback_list, f, ensure_ascii=False, indent=2)

    print(f"\nОбогащено: {updated} записей")

    if updated:
        print("Синхронизируем с Google Sheets...")
        sheets.sync()


if __name__ == "__main__":
    enrich()

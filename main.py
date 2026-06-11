import sys
import time
from dotenv import load_dotenv
load_dotenv()

import scraper
import evaluator
import notifier
import storage
import feedback

TEST_MODE = "--test" in sys.argv
BOOTSTRAP_MODE = "--bootstrap" in sys.argv
MAX_EVALUATE = 25  # максимум оценок через Claude за один запуск

# --pages N — ограничить количество страниц на категорию
_pages_arg = next((sys.argv[i+1] for i, a in enumerate(sys.argv) if a == "--pages"), None)
MAX_PAGES = int(_pages_arg) if _pages_arg else (1 if TEST_MODE else None)


def bootstrap():
    """Помечает все текущие объявления как виденные без оценки."""
    print("Bootstrap: собираем все объявления и помечаем как виденные...")
    seen = storage.load_seen()
    total = 0
    for listing in scraper.scrape_all_listings_iter():
        storage.mark_seen(listing["link"], seen)
        total += 1
        if total % 100 == 0:
            storage.save_seen(seen)
            print(f"  Сохранено: {total}")
    storage.save_seen(seen)
    print(f"Готово. Помечено: {total} объявлений. Теперь будут отслеживаться только новые.")


def run():
    n = feedback.collect_feedback()
    if n:
        print(f"Получена обратная связь: {n} новых записей")

    print("Загружаем виденные объявления...")
    seen = storage.load_seen()
    print(f"Уже видели: {len(seen)} объявлений")

    pages_label = f" (страниц: {MAX_PAGES})" if MAX_PAGES else ""
    print(f"Скрапим...{pages_label}")
    all_listings = scraper.scrape_all_listings(max_pages=MAX_PAGES)

    new_listings = [l for l in all_listings if storage.is_new(l["link"], seen)]
    print(f"Новых объявлений: {len(new_listings)}")

    if not new_listings:
        print("Ничего нового.")
        return

    evaluated = 0
    good = 0
    for i, listing in enumerate(new_listings, 1):
        print(f"[{i}/{len(new_listings)}] {listing['title'][:60]}")

        details = scraper.scrape_listing_details(listing["link"])
        listing.update(details)

        if not evaluator.quick_filter(listing):
            print("  → пропуск (Haiku)")
            storage.mark_seen(listing["link"], seen)
            time.sleep(0.3)
            continue

        if evaluated >= MAX_EVALUATE:
            print(f"  → лимит {MAX_EVALUATE} оценок за запуск достигнут, пропускаем остальные")
            break

        result = evaluator.evaluate_listing(listing)
        verdict = result.get("verdict", "?")
        model = result.get("model_name") or ""
        print(f"  → {verdict} {model}")
        evaluated += 1

        if verdict in ("ДА", "ВОЗМОЖНО"):
            params = result.get("params", {})
            unknowns = sum(1 for p in params.values() if p.get("match") == "❓")
            if unknowns >= 7:
                print("  → пропуск (слишком мало данных в объявлении)")
            else:
                notifier.send_listing(listing, result)
                good += 1

        storage.mark_seen(listing["link"], seen)
        time.sleep(1)

    storage.save_seen(seen)
    print(f"\nГотово. Оценено: {evaluated}, отправлено в Telegram: {good}.")


if __name__ == "__main__":
    if BOOTSTRAP_MODE:
        bootstrap()
    else:
        run()

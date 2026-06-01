import re
import time
import requests
from bs4 import BeautifulSoup

OLX_URLS = [
    "https://www.olx.pl/sport-hobby/rowery/rowery-crossowe/warszawa/?search%5Bdist%5D=75&search%5Bfilter_float_price:from%5D=500&search%5Bfilter_float_price:to%5D=1500",
    "https://www.olx.pl/sport-hobby/rowery/rowery-trekkingowe/warszawa/?search%5Bdist%5D=75&search%5Bfilter_float_price:from%5D=500&search%5Bfilter_float_price:to%5D=1500",
    "https://www.olx.pl/sport-hobby/rowery/rowery-gravel/warszawa/?search%5Bdist%5D=75&search%5Bfilter_float_price:from%5D=500&search%5Bfilter_float_price:to%5D=1500",
]

ALLEGRO_URLS = [
    "https://allegrolokalnie.pl/oferty/rowery/crossowe-125055/warszawa?price_from=500&price_to=1500&odleglosc=75&zrodlo=allegro&zrodlo=lokalnie",
    "https://allegrolokalnie.pl/oferty/rowery/trekkingowe-16485/warszawa?price_from=500&price_to=1500&odleglosc=75&zrodlo=allegro&zrodlo=lokalnie",
    "https://allegrolokalnie.pl/oferty/rowery/przelajowe-gravel-254383/warszawa?price_from=500&price_to=1500&odleglosc=75&zrodlo=allegro&zrodlo=lokalnie",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pl-PL,pl;q=0.9",
}


# ── OLX ──────────────────────────────────────────────────────────────────────

def _scrape_olx_details(url: str) -> dict:
    result = {"description": "", "params": [], "photos": []}
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")

        desc_tag = soup.find("div", attrs={"data-cy": "ad_description"})
        if desc_tag:
            result["description"] = desc_tag.get_text(separator=" ", strip=True)

        params_container = soup.find(attrs={"data-testid": "ad-parameters-container"})
        if params_container:
            for p in params_container.find_all("p"):
                text = p.get_text(strip=True)
                if text and ":" in text:
                    result["params"].append(text)

        for img in soup.find_all("img"):
            src = img.get("src", "")
            if "apollo.olxcdn" in src and "image" in src:
                result["photos"].append(src)
        result["photos"] = result["photos"][:5]

    except Exception:
        pass
    return result


def _scrape_olx_page(base_url: str, page: int) -> list[dict]:
    url = base_url + f"&page={page}"
    response = requests.get(url, headers=HEADERS, timeout=10)
    soup = BeautifulSoup(response.text, "html.parser")

    results = []
    for listing in soup.find_all("div", attrs={"data-cy": "l-card"}):
        title_tag = listing.find("h4")
        title = title_tag.text.strip() if title_tag else "—"

        price_tag = listing.find("p", attrs={"data-testid": "ad-price"})
        price = price_tag.text.strip() if price_tag else "—"

        link_tag = listing.find("a")
        if link_tag and link_tag.get("href", "").startswith("/"):
            link = "https://www.olx.pl" + link_tag["href"]
        elif link_tag:
            link = link_tag.get("href", "—")
        else:
            link = "—"

        results.append({"title": title, "price": price, "link": link, "source": "olx"})

    return results


def _scrape_olx_all(max_pages: int = None) -> list[dict]:
    seen_links = set()
    all_listings = []

    for base_url in OLX_URLS:
        category = base_url.split("/rowery/")[1].split("/")[0]
        print(f"\n[OLX] {category}")
        page = 1

        while True:
            print(f"  Страница {page}...", end=" ", flush=True)
            listings = _scrape_olx_page(base_url, page)

            if not listings:
                print("пусто.")
                break

            new = [l for l in listings if l["link"] not in seen_links]
            for l in new:
                seen_links.add(l["link"])
            all_listings.extend(new)
            print(f"найдено {len(listings)}, новых {len(new)}")

            if max_pages and page >= max_pages:
                break

            page += 1
            time.sleep(1)

    return all_listings, seen_links


# ── Allegro Lokalnie ──────────────────────────────────────────────────────────

def _scrape_allegro_details(url: str) -> dict:
    result = {"description": "", "params": [], "photos": []}
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")

        desc_tag = soup.find("div", class_="mlc-offer__description")
        if desc_tag:
            result["description"] = desc_tag.get_text(separator=" ", strip=True)

        for row in soup.find_all("tr", class_="mlc-params__parameter"):
            cells = row.find_all("td")
            if len(cells) >= 2:
                label = cells[0].get_text(strip=True)
                value = cells[1].get_text(strip=True)
                if label and value:
                    result["params"].append(f"{label}: {value}")

        seen_hashes = set()
        for img in soup.find_all("img"):
            src = img.get("src", "")
            if "allegroimg.com" not in src:
                continue
            # Нормализуем к размеру s512x512
            normalized = re.sub(r's\d+x\d+', 's512x512', src)
            img_hash = src.split("/")[-1]
            if img_hash not in seen_hashes:
                seen_hashes.add(img_hash)
                result["photos"].append(normalized)
        result["photos"] = result["photos"][:5]

    except Exception:
        pass
    return result


def _scrape_allegro_page(base_url: str, page: int) -> tuple[list[dict], int]:
    """Возвращает (объявления, всего_страниц)."""
    url = base_url + f"&p={page}"
    response = requests.get(url, headers=HEADERS, timeout=20)
    soup = BeautifulSoup(response.text, "html.parser")

    total_pages = 1
    nav = soup.find("nav", class_="ml-pagination")
    if nav:
        m = re.search(r"z\s+(\d+)", nav.get_text())
        if m:
            total_pages = int(m.group(1))

    results = []
    for article in soup.find_all("article", class_="mlc-itembox__container"):
        title_tag = article.find("h3")
        title = title_tag.get_text(strip=True) if title_tag else "—"

        price_tag = article.find("div", class_="mlc-itembox__price")
        price = price_tag.get_text(strip=True) if price_tag else "—"

        link_tag = article.find("a", class_="mlc-card")
        if link_tag and link_tag.get("href", "").startswith("/"):
            link = "https://allegrolokalnie.pl" + link_tag["href"]
        elif link_tag:
            link = link_tag.get("href", "—")
        else:
            link = "—"

        results.append({"title": title, "price": price, "link": link, "source": "allegro"})

    return results, total_pages


def _scrape_allegro_all(seen_links: set, max_pages: int = None) -> list[dict]:
    all_listings = []

    for base_url in ALLEGRO_URLS:
        category = base_url.split("/rowery/")[1].split("/")[0]
        print(f"\n[Allegro] {category}")
        page = 1

        while True:
            if max_pages and page > max_pages:
                break

            print(f"  Страница {page}...", end=" ", flush=True)
            try:
                listings, total_pages = _scrape_allegro_page(base_url, page)
            except Exception as e:
                print(f"ошибка: {e}")
                break

            if not listings:
                print("пусто.")
                break

            new = [l for l in listings if l["link"] not in seen_links]
            for l in new:
                seen_links.add(l["link"])
            all_listings.extend(new)
            print(f"найдено {len(listings)}, новых {len(new)} (стр. {page}/{total_pages})")

            if page >= total_pages:
                break

            page += 1
            time.sleep(2)

    return all_listings


# ── Public API ────────────────────────────────────────────────────────────────

def scrape_listing_details(url: str) -> dict:
    if "allegrolokalnie.pl" in url:
        return _scrape_allegro_details(url)
    return _scrape_olx_details(url)


def scrape_all_listings(max_pages: int = None) -> list[dict]:
    """Скрапит OLX и Allegro Lokalnie, возвращает дедуплицированный список."""
    olx_listings, seen_links = _scrape_olx_all(max_pages)
    allegro_listings = _scrape_allegro_all(seen_links, max_pages)

    total = olx_listings + allegro_listings
    print(f"\nИтого: OLX {len(olx_listings)} + Allegro {len(allegro_listings)} = {len(total)} объявлений")
    return total


def scrape_all():
    for item in scrape_all_listings():
        print(f"[{item['source']}] {item['title']} | {item['price']}")
        print(f"  {item['link']}")
        print("-" * 60)


if __name__ == "__main__":
    scrape_all()

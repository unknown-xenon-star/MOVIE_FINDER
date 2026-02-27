#!/usr/bin/env python3
import argparse
import csv
import json
import re
import time
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.imdb.com/search/title/"
QUERY = "title_type=feature&genres=horror&country_of_origin=IN"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def extract_imdb_id(url: str) -> Optional[str]:
    match = re.search(r"/title/(tt\d+)/", url)
    return match.group(1) if match else None


def parse_int_from_text(text: str) -> Optional[int]:
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else None


def parse_items(html: str) -> List[Dict]:
    soup = BeautifulSoup(html, "html.parser")
    items = []
    cards = soup.select("li.ipc-metadata-list-summary-item")

    for card in cards:
        title_link = card.select_one("a.ipc-title-link-wrapper")
        title_text = card.select_one("h3.ipc-title__text")
        if not title_link or not title_text:
            continue

        title_url = urljoin("https://www.imdb.com", title_link.get("href", ""))
        imdb_id = extract_imdb_id(title_url)
        if not imdb_id:
            continue

        metadata = card.select("div.dli-title-metadata span")
        year = parse_int_from_text(metadata[0].get_text(strip=True)) if len(metadata) > 0 else None
        runtime = metadata[1].get_text(strip=True) if len(metadata) > 1 else None

        rating_tag = card.select_one("span.ipc-rating-star--rating")
        votes_tag = card.select_one("span.ipc-rating-star--voteCount")
        poster_tag = card.select_one("img.ipc-image")

        genres = [g.get_text(strip=True) for g in card.select("span.ipc-chip__text")]

        items.append(
            {
                "imdb_id": imdb_id,
                "title": title_text.get_text(strip=True),
                "year": year,
                "runtime": runtime,
                "rating": float(rating_tag.get_text(strip=True)) if rating_tag else None,
                "votes": parse_int_from_text(votes_tag.get_text(strip=True)) if votes_tag else None,
                "genres": ", ".join(genres) if genres else None,
                "imdb_url": title_url.split("?")[0],
                "poster_url": poster_tag.get("src") if poster_tag else None,
            }
        )

    return items


def find_next_start(html: str) -> Optional[int]:
    soup = BeautifulSoup(html, "html.parser")
    next_link = soup.select_one('a[aria-label="Next"]')
    if not next_link:
        return None

    href = next_link.get("href", "")
    parsed = urlparse(href)
    start_values = parse_qs(parsed.query).get("start")
    if not start_values:
        return None

    try:
        return int(start_values[0])
    except ValueError:
        return None


def scrape(max_pages: Optional[int], sleep_seconds: float, out_dir: Path) -> List[Dict]:
    session = requests.Session()
    session.headers.update(HEADERS)

    data_dir = out_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    all_items: List[Dict] = []
    visited_ids = set()
    current_start = 1
    page_count = 0

    while True:
        if max_pages is not None and page_count >= max_pages:
            break

        page_count += 1
        url = f"{BASE_URL}?{QUERY}&start={current_start}"
        print(f"Scraping page {page_count}: {url}")

        response = session.get(url, timeout=30)
        response.raise_for_status()
        html = response.text

        items = parse_items(html)
        if not items:
            print("No items found on this page. Stopping.")
            break

        for item in items:
            if item["imdb_id"] in visited_ids:
                continue
            visited_ids.add(item["imdb_id"])

            all_items.append(item)

        next_start = find_next_start(html)
        if not next_start or next_start == current_start:
            break

        current_start = next_start
        time.sleep(sleep_seconds)

    json_path = data_dir / "movies.json"
    csv_path = data_dir / "movies.csv"

    json_path.write_text(json.dumps(all_items, indent=2, ensure_ascii=False), encoding="utf-8")

    fieldnames = [
        "imdb_id",
        "title",
        "year",
        "runtime",
        "rating",
        "votes",
        "genres",
        "imdb_url",
        "poster_url",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_items)

    print(f"Saved {len(all_items)} movies")
    print(f"JSON: {json_path}")
    print(f"CSV:  {csv_path}")

    return all_items


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape Indian horror feature films from IMDb and download posters."
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Maximum number of pages to scrape (default: all pages).",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=1.0,
        help="Delay between page requests in seconds (default: 1.0).",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("output"),
        help="Output directory (default: output).",
    )
    args = parser.parse_args()
    scrape(args.max_pages, args.sleep, args.out_dir)


if __name__ == "__main__":
    main()

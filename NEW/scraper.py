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


def pick_from_srcset(srcset: str) -> Optional[str]:
    if not srcset:
        return None

    candidates = []
    for part in srcset.split(","):
        chunk = part.strip()
        if not chunk:
            continue
        fields = chunk.split()
        url = fields[0] if fields else ""
        scale = 0.0
        if len(fields) > 1:
            descriptor = fields[1]
            try:
                if descriptor.endswith("x"):
                    scale = float(descriptor[:-1])
                elif descriptor.endswith("w"):
                    scale = float(descriptor[:-1])
            except ValueError:
                scale = 0.0
        candidates.append((scale, url))

    if not candidates:
        return None
    return sorted(candidates, key=lambda x: x[0])[-1][1]


def normalize_poster_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    if url.startswith("data:"):
        return None
    if url.startswith("//"):
        url = f"https:{url}"

    # Strip IMDb sizing modifiers so the URL is not tied to lazy-render variants.
    if "m.media-amazon.com/images/" in url:
        url = re.sub(r"\._V1_.*?(\.[a-zA-Z0-9]+)$", r"._V1_\1", url)
    return url


def extract_poster_url(card) -> Optional[str]:
    img = card.select_one("img.ipc-image")
    if img:
        candidates = [
            img.get("data-src"),
            img.get("data-image-src"),
            img.get("data-lazy-src"),
            pick_from_srcset(img.get("data-srcset", "")),
            pick_from_srcset(img.get("srcset", "")),
            img.get("src"),
        ]
        for candidate in candidates:
            normalized = normalize_poster_url(candidate)
            if normalized:
                return normalized

    # Fallback for pages where images are inside noscript tags.
    noscript_img = card.select_one("noscript img")
    if noscript_img:
        fallback = normalize_poster_url(noscript_img.get("src"))
        if fallback:
            return fallback

    return None


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
        poster_url = extract_poster_url(card)

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
                "poster_url": poster_url,
            }
        )

    return items


def find_next_start(html: str, current_start: int) -> Optional[int]:
    soup = BeautifulSoup(html, "html.parser")
    starts = set()

    for link in soup.select('a[href*="start="]'):
        href = link.get("href", "")
        parsed = urlparse(href)
        start_values = parse_qs(parsed.query).get("start")
        if not start_values:
            continue
        try:
            starts.add(int(start_values[0]))
        except ValueError:
            continue

    higher = sorted(s for s in starts if s > current_start)
    return higher[0] if higher else None


def scrape(
    max_pages: Optional[int],
    sleep_seconds: float,
    out_dir: Path,
    page_size: int,
) -> List[Dict]:

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

        url = f"{BASE_URL}?{QUERY}&count={page_size}&start={current_start}"
        print(f"Scraping page {page_count}: {url}")

        response = session.get(url, timeout=30)
        response.raise_for_status()

        html = response.text
        items = parse_items(html)

        if not items:
            print("No items found. Stopping.")
            break

        new_on_page = 0
        for item in items:
            if item["imdb_id"] in visited_ids:
                continue
            visited_ids.add(item["imdb_id"])
            new_on_page += 1
            all_items.append(item)

        print(f"Found {new_on_page} new items")

        # If fewer results returned than requested, we reached end
        if len(items) < page_size:
            print("Last page reached.")
            break

        current_start += page_size
        time.sleep(sleep_seconds)

    # Save results
    json_path = data_dir / "movies.json"
    csv_path = data_dir / "movies.csv"

    json_path.write_text(
        json.dumps(all_items, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

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
    parser.add_argument(
        "--page-size",
        type=int,
        default=50,
        help="Results per request (default: 50).",
    )
    args = parser.parse_args()
    scrape(args.max_pages, args.sleep, args.out_dir, args.page_size)


if __name__ == "__main__":
    main()

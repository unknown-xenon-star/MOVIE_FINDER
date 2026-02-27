#!/usr/bin/env python3
"""Scrape horror movie titles from Wikipedia category pages (2000-2015)."""

from __future__ import annotations

import argparse
import csv
import time
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://en.wikipedia.org"
DEFAULT_OUTPUT = "horror_movies_2000_2015.csv"
REQUEST_TIMEOUT = 20
REQUEST_DELAY_SECONDS = 0.5


@dataclass(frozen=True)
class MovieRecord:
    year: int
    title: str
    movie_page_url: str
    poster_url: str
    source_url: str


def category_url_for_year(year: int) -> str:
    return f"{BASE_URL}/wiki/Category:{year}_horror_films"


def fetch_html(session: requests.Session, url: str) -> str:
    response = session.get(url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.text


def extract_titles_and_next_page(html: str) -> tuple[list[tuple[str, str]], str | None]:
    soup = BeautifulSoup(html, "lxml")
    mw_pages = soup.select_one("#mw-pages")
    if mw_pages is None:
        return [], None

    titles: list[tuple[str, str]] = []
    for anchor in mw_pages.select("li a"):
        title = anchor.get_text(strip=True)
        href = anchor.get("href")
        if not title or not href:
            continue
        titles.append((title, urljoin(BASE_URL, href)))

    next_page_url = None
    for anchor in mw_pages.select("a"):
        if anchor.get_text(strip=True).lower() == "next page":
            href = anchor.get("href")
            if href:
                next_page_url = urljoin(BASE_URL, href)
            break

    return titles, next_page_url


def extract_poster_url(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")

    # Wikipedia pages usually store movie posters in infobox images.
    image = soup.select_one("table.infobox img")
    if image and image.get("src"):
        src = image["src"]
        if src.startswith("//"):
            return f"https:{src}"
        return urljoin(BASE_URL, src)

    og_image = soup.select_one('meta[property="og:image"]')
    if og_image and og_image.get("content"):
        return og_image["content"]

    return ""


def fetch_poster_url(session: requests.Session, movie_page_url: str) -> str:
    try:
        html = fetch_html(session, movie_page_url)
    except requests.RequestException:
        return ""
    return extract_poster_url(html)


def scrape_year_titles(session: requests.Session, year: int) -> list[MovieRecord]:
    url = category_url_for_year(year)
    records: list[MovieRecord] = []
    seen_titles: set[str] = set()
    poster_cache: dict[str, str] = {}

    while url:
        html = fetch_html(session, url)
        titles, next_page = extract_titles_and_next_page(html)

        for title, movie_page_url in titles:
            if title in seen_titles:
                continue
            seen_titles.add(title)
            if movie_page_url not in poster_cache:
                poster_cache[movie_page_url] = fetch_poster_url(session, movie_page_url)
                time.sleep(REQUEST_DELAY_SECONDS)
            records.append(
                MovieRecord(
                    year=year,
                    title=title,
                    movie_page_url=movie_page_url,
                    poster_url=poster_cache[movie_page_url],
                    source_url=url,
                )
            )

        url = next_page
        if url:
            time.sleep(REQUEST_DELAY_SECONDS)

    return records


def write_csv(path: str, records: Iterable[MovieRecord]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["year", "title", "movie_page_url", "poster_url", "source_url"])
        for record in records:
            writer.writerow(
                [
                    record.year,
                    record.title,
                    record.movie_page_url,
                    record.poster_url,
                    record.source_url,
                ]
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape horror movies from Wikipedia category pages for years 2000-2015."
    )
    parser.add_argument("--start-year", type=int, default=2000, help="First year to scrape (default: 2000)")
    parser.add_argument("--end-year", type=int, default=2015, help="Last year to scrape, inclusive (default: 2015)")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help=f"Output CSV file (default: {DEFAULT_OUTPUT})")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.start_year > args.end_year:
        raise ValueError("start-year must be less than or equal to end-year")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/123.0 Safari/537.36"
        )
    }

    all_records: list[MovieRecord] = []
    with requests.Session() as session:
        session.headers.update(headers)
        for year in range(args.start_year, args.end_year + 1):
            year_records = scrape_year_titles(session, year)
            all_records.extend(year_records)
            time.sleep(REQUEST_DELAY_SECONDS)

    all_records.sort(key=lambda rec: (rec.year, rec.title.lower()))
    write_csv(args.output, all_records)
    print(f"Saved {len(all_records)} records to {args.output}")


if __name__ == "__main__":
    main()

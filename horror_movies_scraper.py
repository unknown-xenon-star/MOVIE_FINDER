#!/usr/bin/env python3
"""Scrape Indian movie titles and posters from Wikipedia (2000-2015).

Supports checkpoint-based pause/resume.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://en.wikipedia.org"
DEFAULT_OUTPUT = "indian_movies_2000_2015.csv"
DEFAULT_CHECKPOINT = "indian_movies_scrape_progress.json"
REQUEST_TIMEOUT = 20
REQUEST_DELAY_SECONDS = 0.5

LANGUAGE_CATEGORY_TEMPLATES = {
    "indian": "Category:{year}_Indian_films",
    "tamil": "Category:{year}_Tamil-language_films",
    "telugu": "Category:{year}_Telugu-language_films",
    "malayalam": "Category:{year}_Malayalam-language_films",
    "kannada": "Category:{year}_Kannada-language_films",
    "hindi": "Category:{year}_Hindi-language_films",
    "bengali": "Category:{year}_Bengali-language_films",
    "marathi": "Category:{year}_Marathi-language_films",
    "punjabi": "Category:{year}_Punjabi-language_films",
    "gujarati": "Category:{year}_Gujarati-language_films",
    "odia": "Category:{year}_Odia-language_films",
    "assamese": "Category:{year}_Assamese-language_films",
    "bhojpuri": "Category:{year}_Bhojpuri-language_films",
}

SOUTH_PRIORITY_LANGUAGES = ["tamil", "telugu", "malayalam", "kannada"]
DEFAULT_LANGUAGES = [
    "tamil",
    "telugu",
    "malayalam",
    "kannada",
    "indian",
    "hindi",
    "bengali",
    "marathi",
    "punjabi",
    "gujarati",
    "odia",
    "assamese",
    "bhojpuri",
]


def log(message: str, verbose: bool) -> None:
    if verbose:
        print(message)


@dataclass(frozen=True)
class ScrapeTask:
    year: int
    language: str


@dataclass(frozen=True)
class MovieRecord:
    year: int
    language: str
    title: str
    movie_page_url: str
    poster_url: str
    description: str
    source_url: str


def task_key(task: ScrapeTask) -> str:
    return f"{task.year}:{task.language}"


def category_url_for_task(task: ScrapeTask) -> str:
    template = LANGUAGE_CATEGORY_TEMPLATES[task.language]
    return f"{BASE_URL}/wiki/{template.format(year=task.year)}"


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


def extract_description(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    content = soup.select_one("div.mw-parser-output")
    if content:
        for para in content.select("p"):
            text = para.get_text(" ", strip=True)
            if len(text) >= 60:
                return " ".join(text.split())

    meta_desc = soup.select_one('meta[property="og:description"]')
    if meta_desc and meta_desc.get("content"):
        return " ".join(meta_desc["content"].split())

    return ""


def fetch_movie_details(session: requests.Session, movie_page_url: str, verbose: bool) -> tuple[str, str]:
    log(f"    Fetching details: {movie_page_url}", verbose)
    try:
        html = fetch_html(session, movie_page_url)
    except requests.RequestException:
        log("    Details fetch failed; using empty poster/description", verbose)
        return "", ""
    return extract_poster_url(html), extract_description(html)


def save_checkpoint(
    path: Path,
    args: argparse.Namespace,
    completed_tasks: set[str],
    records: list[MovieRecord],
    movie_details_cache: dict[str, dict[str, str]],
) -> None:
    data = {
        "version": 1,
        "config": {
            "start_year": args.start_year,
            "end_year": args.end_year,
            "languages": args.languages,
        },
        "completed_tasks": sorted(completed_tasks),
        "records": [asdict(record) for record in records],
        "movie_details_cache": movie_details_cache,
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_checkpoint(
    path: Path, args: argparse.Namespace
) -> tuple[set[str], list[MovieRecord], dict[str, dict[str, str]]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    expected = {
        "start_year": args.start_year,
        "end_year": args.end_year,
        "languages": args.languages,
    }
    if raw.get("config") != expected:
        raise ValueError(
            "Checkpoint config mismatch. Use matching args or delete checkpoint file."
        )

    completed = set(raw.get("completed_tasks", []))
    records = []
    for item in raw.get("records", []):
        records.append(
            MovieRecord(
                year=item["year"],
                language=item["language"],
                title=item["title"],
                movie_page_url=item["movie_page_url"],
                poster_url=item.get("poster_url", ""),
                description=item.get("description", ""),
                source_url=item["source_url"],
            )
        )

    cached = raw.get("movie_details_cache")
    if cached is None:
        # Backward compatibility with older checkpoints that only stored posters.
        legacy_posters = dict(raw.get("poster_cache", {}))
        cached = {url: {"poster_url": poster, "description": ""} for url, poster in legacy_posters.items()}
    movie_details_cache = dict(cached)
    return completed, records, movie_details_cache


def scrape_task(
    session: requests.Session,
    task: ScrapeTask,
    seen_titles: set[tuple[int, str]],
    movie_details_cache: dict[str, dict[str, str]],
    verbose: bool,
) -> list[MovieRecord]:
    url = category_url_for_task(task)
    page_number = 1
    task_records: list[MovieRecord] = []

    while url:
        log(f"Scraping {task.language} {task.year} page {page_number}: {url}", verbose)
        try:
            html = fetch_html(session, url)
        except requests.RequestException:
            log(f"  Could not fetch category page for {task.language} {task.year}; skipping task", verbose)
            break
        titles, next_page = extract_titles_and_next_page(html)
        log(f"  Found {len(titles)} titles", verbose)

        for title, movie_page_url in titles:
            dedupe_key = (task.year, title.lower())
            if dedupe_key in seen_titles:
                continue
            seen_titles.add(dedupe_key)

            if movie_page_url not in movie_details_cache:
                poster_url, description = fetch_movie_details(session, movie_page_url, verbose)
                movie_details_cache[movie_page_url] = {
                    "poster_url": poster_url,
                    "description": description,
                }
                time.sleep(REQUEST_DELAY_SECONDS)

            task_records.append(
                MovieRecord(
                    year=task.year,
                    language=task.language,
                    title=title,
                    movie_page_url=movie_page_url,
                    poster_url=movie_details_cache[movie_page_url].get("poster_url", ""),
                    description=movie_details_cache[movie_page_url].get("description", ""),
                    source_url=url,
                )
            )

        url = next_page
        page_number += 1
        if url:
            time.sleep(REQUEST_DELAY_SECONDS)

    log(f"Completed {task.language} {task.year}: {len(task_records)} titles", verbose)
    return task_records


def write_csv(path: str, records: Iterable[MovieRecord]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(
            ["year", "language", "title", "movie_page_url", "poster_url", "description", "source_url"]
        )
        for record in records:
            writer.writerow(
                [
                    record.year,
                    record.language,
                    record.title,
                    record.movie_page_url,
                    record.poster_url,
                    record.description,
                    record.source_url,
                ]
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape Indian movie titles from Wikipedia categories with poster URLs."
    )
    parser.add_argument("--start-year", type=int, default=2000, help="First year to scrape (default: 2000)")
    parser.add_argument("--end-year", type=int, default=2015, help="Last year to scrape, inclusive (default: 2015)")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help=f"Output CSV file (default: {DEFAULT_OUTPUT})")
    parser.add_argument(
        "--languages",
        nargs="+",
        default=DEFAULT_LANGUAGES,
        choices=sorted(LANGUAGE_CATEGORY_TEMPLATES.keys()),
        help="Indian film category sources to scrape",
    )
    parser.add_argument(
        "--prefer-south",
        action="store_true",
        default=True,
        help="Scrape South Indian categories first (default: enabled)",
    )
    parser.add_argument(
        "--no-prefer-south",
        action="store_false",
        dest="prefer_south",
        help="Disable South-first scraping order",
    )
    parser.add_argument("--verbose", action="store_true", help="Print progress logs")
    parser.add_argument(
        "--checkpoint",
        default=DEFAULT_CHECKPOINT,
        help=f"Checkpoint JSON file for pause/resume (default: {DEFAULT_CHECKPOINT})",
    )
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoint if it exists")
    parser.add_argument(
        "--pause-after",
        type=int,
        default=0,
        help="Pause after N completed tasks and save checkpoint (0 means no manual pause)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.start_year > args.end_year:
        raise ValueError("start-year must be less than or equal to end-year")

    checkpoint_path = Path(args.checkpoint)
    completed_tasks: set[str] = set()
    records: list[MovieRecord] = []
    movie_details_cache: dict[str, dict[str, str]] = {}

    if args.resume and checkpoint_path.exists():
        completed_tasks, records, movie_details_cache = load_checkpoint(checkpoint_path, args)
        print(
            f"Resumed from checkpoint: {len(completed_tasks)} tasks done, "
            f"{len(records)} records loaded"
        )

    seen_titles = {(record.year, record.title.lower()) for record in records}
    selected_languages = list(dict.fromkeys(args.languages))
    if args.prefer_south:
        input_order = {lang: idx for idx, lang in enumerate(selected_languages)}
        selected_languages.sort(
            key=lambda lang: (0 if lang in SOUTH_PRIORITY_LANGUAGES else 1, input_order[lang])
        )

    tasks = [
        ScrapeTask(year=year, language=language)
        for year in range(args.start_year, args.end_year + 1)
        for language in selected_languages
    ]

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/123.0 Safari/537.36"
        )
    }

    completed_since_start = 0
    try:
        with requests.Session() as session:
            session.headers.update(headers)
            for task in tasks:
                key = task_key(task)
                if key in completed_tasks:
                    log(f"Skipping completed task: {key}", args.verbose)
                    continue

                task_records = scrape_task(session, task, seen_titles, movie_details_cache, args.verbose)
                records.extend(task_records)
                completed_tasks.add(key)
                completed_since_start += 1

                save_checkpoint(checkpoint_path, args, completed_tasks, records, movie_details_cache)

                if args.pause_after > 0 and completed_since_start >= args.pause_after:
                    print(
                        f"Paused after {completed_since_start} new tasks. "
                        f"Resume with: --resume --checkpoint {checkpoint_path}"
                    )
                    write_csv(args.output, sorted(records, key=lambda rec: (rec.year, rec.language, rec.title.lower())))
                    return

                time.sleep(REQUEST_DELAY_SECONDS)

    except KeyboardInterrupt:
        save_checkpoint(checkpoint_path, args, completed_tasks, records, movie_details_cache)
        print(
            f"Interrupted. Progress saved to {checkpoint_path}. "
            f"Resume with: --resume --checkpoint {checkpoint_path}"
        )
        return

    records.sort(key=lambda rec: (rec.year, rec.language, rec.title.lower()))
    write_csv(args.output, records)
    save_checkpoint(checkpoint_path, args, completed_tasks, records, movie_details_cache)
    print(f"Saved {len(records)} records to {args.output}")
    print(f"Checkpoint updated: {checkpoint_path}")


if __name__ == "__main__":
    main()

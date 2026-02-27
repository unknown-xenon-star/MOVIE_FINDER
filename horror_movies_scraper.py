#!/usr/bin/env python3
"""Scrape Indian movie titles, posters, and descriptions from Wikipedia (2000-2015).

Supports checkpoint-based pause/resume and manual recovery for failed tasks.
"""

from __future__ import annotations

import argparse
import concurrent.futures
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
DEFAULT_FAILED_REPORT = "failed_tasks.csv"
REQUEST_TIMEOUT = 20
REQUEST_DELAY_SECONDS = 0.5
DEFAULT_WORKERS = 8

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


def parse_task_id(raw_task_id: str) -> ScrapeTask:
    try:
        year_text, language = raw_task_id.split(":", 1)
    except ValueError as exc:
        raise ValueError(f"Invalid task id '{raw_task_id}'. Use YEAR:LANGUAGE") from exc

    year = int(year_text)
    language = language.strip().lower()
    if language not in LANGUAGE_CATEGORY_TEMPLATES:
        raise ValueError(f"Unknown language '{language}' in task id '{raw_task_id}'")
    return ScrapeTask(year=year, language=language)


def category_url_for_task(task: ScrapeTask) -> str:
    template = LANGUAGE_CATEGORY_TEMPLATES[task.language]
    return f"{BASE_URL}/wiki/{template.format(year=task.year)}"


def fetch_html(session: requests.Session, url: str) -> str:
    response = session.get(url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.text


def fetch_html_url(url: str, headers: dict[str, str]) -> str:
    response = requests.get(url, timeout=REQUEST_TIMEOUT, headers=headers)
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


def fetch_movie_details(movie_page_url: str, headers: dict[str, str]) -> tuple[str, str]:
    try:
        html = fetch_html_url(movie_page_url, headers)
    except requests.RequestException:
        return "", ""
    return extract_poster_url(html), extract_description(html)


def save_checkpoint(
    path: Path,
    args: argparse.Namespace,
    completed_tasks: set[str],
    failed_tasks: dict[str, str],
    records: list[MovieRecord],
    movie_details_cache: dict[str, dict[str, str]],
) -> None:
    data = {
        "version": 2,
        "config": {
            "start_year": args.start_year,
            "end_year": args.end_year,
            "languages": args.languages,
        },
        "completed_tasks": sorted(completed_tasks),
        "failed_tasks": failed_tasks,
        "records": [asdict(record) for record in records],
        "movie_details_cache": movie_details_cache,
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_checkpoint(
    path: Path, args: argparse.Namespace
) -> tuple[set[str], dict[str, str], list[MovieRecord], dict[str, dict[str, str]]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    expected = {
        "start_year": args.start_year,
        "end_year": args.end_year,
        "languages": args.languages,
    }
    if raw.get("config") != expected:
        raise ValueError("Checkpoint config mismatch. Use matching args or delete checkpoint file.")

    completed = set(raw.get("completed_tasks", []))
    failed = dict(raw.get("failed_tasks", {}))

    records: list[MovieRecord] = []
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
        legacy_posters = dict(raw.get("poster_cache", {}))
        cached = {url: {"poster_url": poster, "description": ""} for url, poster in legacy_posters.items()}
    movie_details_cache = dict(cached)

    return completed, failed, records, movie_details_cache


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


def write_failed_tasks(path: Path, failed_tasks: dict[str, str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["task_id", "error"])
        for task_id in sorted(failed_tasks.keys()):
            writer.writerow([task_id, failed_tasks[task_id]])


def load_manual_records(path: Path) -> list[MovieRecord]:
    required = {"year", "language", "title", "movie_page_url", "poster_url", "description", "source_url"}
    records: list[MovieRecord] = []
    with path.open("r", encoding="utf-8", newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            raise ValueError(
                "Manual records CSV must include columns: year, language, title, movie_page_url, "
                "poster_url, description, source_url"
            )

        for row in reader:
            records.append(
                MovieRecord(
                    year=int(row["year"]),
                    language=row["language"].strip().lower(),
                    title=row["title"].strip(),
                    movie_page_url=row["movie_page_url"].strip(),
                    poster_url=row["poster_url"].strip(),
                    description=row["description"].strip(),
                    source_url=row["source_url"].strip(),
                )
            )
    return records


def scrape_task(
    task: ScrapeTask,
    session: requests.Session,
    headers: dict[str, str],
    seen_titles: set[tuple[int, str]],
    movie_details_cache: dict[str, dict[str, str]],
    workers: int,
    request_delay: float,
    verbose: bool,
) -> tuple[list[MovieRecord], bool, str]:
    url = category_url_for_task(task)
    page_number = 1
    task_records: list[MovieRecord] = []
    task_seen_titles: set[str] = set()

    while url:
        log(f"Scraping {task.language} {task.year} page {page_number}: {url}", verbose)
        try:
            html = fetch_html(session, url)
        except requests.RequestException as exc:
            log(f"  Could not fetch category page for {task.language} {task.year}; task failed", verbose)
            return task_records, False, str(exc)

        titles, next_page = extract_titles_and_next_page(html)
        log(f"  Found {len(titles)} titles", verbose)

        fresh_entries: list[tuple[str, str]] = []
        uncached_urls: set[str] = set()
        for title, movie_page_url in titles:
            title_key = title.lower()
            global_key = (task.year, title_key)
            if global_key in seen_titles or title_key in task_seen_titles:
                continue
            seen_titles.add(global_key)
            task_seen_titles.add(title_key)
            fresh_entries.append((title, movie_page_url))
            if movie_page_url not in movie_details_cache:
                uncached_urls.add(movie_page_url)

        if uncached_urls:
            log(f"  Fetching {len(uncached_urls)} detail pages with {workers} workers", verbose)
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
                future_by_url = {
                    executor.submit(fetch_movie_details, movie_page_url, headers): movie_page_url
                    for movie_page_url in uncached_urls
                }
                for future in concurrent.futures.as_completed(future_by_url):
                    movie_page_url = future_by_url[future]
                    poster_url, description = future.result()
                    movie_details_cache[movie_page_url] = {
                        "poster_url": poster_url,
                        "description": description,
                    }

        for title, movie_page_url in fresh_entries:
            details = movie_details_cache.get(movie_page_url, {"poster_url": "", "description": ""})
            task_records.append(
                MovieRecord(
                    year=task.year,
                    language=task.language,
                    title=title,
                    movie_page_url=movie_page_url,
                    poster_url=details.get("poster_url", ""),
                    description=details.get("description", ""),
                    source_url=url,
                )
            )

        url = next_page
        page_number += 1
        if url:
            time.sleep(request_delay)

    log(f"Completed {task.language} {task.year}: {len(task_records)} titles", verbose)
    return task_records, True, ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape Indian movie titles from Wikipedia categories with poster and description."
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
    parser.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_WORKERS,
        help=f"Concurrent workers for movie details (default: {DEFAULT_WORKERS})",
    )
    parser.add_argument(
        "--request-delay",
        type=float,
        default=REQUEST_DELAY_SECONDS,
        help=f"Delay between category requests in seconds (default: {REQUEST_DELAY_SECONDS})",
    )
    parser.add_argument(
        "--failed-only",
        action="store_true",
        help="Scrape only tasks that are marked failed in checkpoint (use with --resume)",
    )
    parser.add_argument(
        "--manual-complete-task",
        action="append",
        default=[],
        help="Mark task as completed manually. Format YEAR:LANGUAGE (repeatable)",
    )
    parser.add_argument(
        "--manual-records",
        default="",
        help="Manual records CSV to import (same columns as output CSV)",
    )
    parser.add_argument(
        "--failed-report",
        default=DEFAULT_FAILED_REPORT,
        help=f"Failed tasks report CSV (default: {DEFAULT_FAILED_REPORT})",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.start_year > args.end_year:
        raise ValueError("start-year must be less than or equal to end-year")
    if args.workers < 1:
        raise ValueError("workers must be >= 1")
    if args.request_delay < 0:
        raise ValueError("request-delay must be >= 0")

    checkpoint_path = Path(args.checkpoint)
    failed_report_path = Path(args.failed_report)

    completed_tasks: set[str] = set()
    failed_tasks: dict[str, str] = {}
    records: list[MovieRecord] = []
    movie_details_cache: dict[str, dict[str, str]] = {}

    if args.resume and checkpoint_path.exists():
        completed_tasks, failed_tasks, records, movie_details_cache = load_checkpoint(checkpoint_path, args)
        print(
            f"Resumed from checkpoint: {len(completed_tasks)} completed, "
            f"{len(failed_tasks)} failed, {len(records)} records loaded"
        )

    for raw_task_id in args.manual_complete_task:
        task = parse_task_id(raw_task_id)
        key = task_key(task)
        completed_tasks.add(key)
        failed_tasks.pop(key, None)

    if args.manual_records:
        imported = load_manual_records(Path(args.manual_records))
        existing = {(record.year, record.title.lower()): idx for idx, record in enumerate(records)}
        for record in imported:
            dedupe_key = (record.year, record.title.lower())
            if dedupe_key in existing:
                records[existing[dedupe_key]] = record
            else:
                records.append(record)
                existing[dedupe_key] = len(records) - 1
            if record.movie_page_url:
                movie_details_cache[record.movie_page_url] = {
                    "poster_url": record.poster_url,
                    "description": record.description,
                }
        print(f"Imported {len(imported)} manual records from {args.manual_records}")

    seen_titles = {(record.year, record.title.lower()) for record in records}

    selected_languages = list(dict.fromkeys(args.languages))
    if args.prefer_south:
        input_order = {lang: idx for idx, lang in enumerate(selected_languages)}
        selected_languages.sort(key=lambda lang: (0 if lang in SOUTH_PRIORITY_LANGUAGES else 1, input_order[lang]))

    all_tasks = [
        ScrapeTask(year=year, language=language)
        for year in range(args.start_year, args.end_year + 1)
        for language in selected_languages
    ]

    if args.failed_only:
        failed_set = set(failed_tasks.keys())
        tasks = [task for task in all_tasks if task_key(task) in failed_set]
    else:
        tasks = all_tasks

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

                task_records, task_ok, task_error = scrape_task(
                    task=task,
                    session=session,
                    headers=headers,
                    seen_titles=seen_titles,
                    movie_details_cache=movie_details_cache,
                    workers=args.workers,
                    request_delay=args.request_delay,
                    verbose=args.verbose,
                )
                records.extend(task_records)
                if task_ok:
                    completed_tasks.add(key)
                    failed_tasks.pop(key, None)
                    completed_since_start += 1
                else:
                    failed_tasks[key] = task_error or "unknown_error"

                save_checkpoint(checkpoint_path, args, completed_tasks, failed_tasks, records, movie_details_cache)
                write_failed_tasks(failed_report_path, failed_tasks)

                if args.pause_after > 0 and completed_since_start >= args.pause_after:
                    records.sort(key=lambda rec: (rec.year, rec.language, rec.title.lower()))
                    write_csv(args.output, records)
                    print(
                        f"Paused after {completed_since_start} successful tasks. "
                        f"Resume with: --resume --checkpoint {checkpoint_path}"
                    )
                    print(f"Failed report: {failed_report_path}")
                    return

                time.sleep(args.request_delay)

    except KeyboardInterrupt:
        save_checkpoint(checkpoint_path, args, completed_tasks, failed_tasks, records, movie_details_cache)
        write_failed_tasks(failed_report_path, failed_tasks)
        print(
            f"Interrupted. Progress saved to {checkpoint_path}. "
            f"Resume with: --resume --checkpoint {checkpoint_path}"
        )
        print(f"Failed report: {failed_report_path}")
        return

    records.sort(key=lambda rec: (rec.year, rec.language, rec.title.lower()))
    write_csv(args.output, records)
    save_checkpoint(checkpoint_path, args, completed_tasks, failed_tasks, records, movie_details_cache)
    write_failed_tasks(failed_report_path, failed_tasks)

    print(f"Saved {len(records)} records to {args.output}")
    print(f"Checkpoint updated: {checkpoint_path}")
    print(f"Failed tasks report: {failed_report_path} ({len(failed_tasks)} tasks)")


if __name__ == "__main__":
    main()

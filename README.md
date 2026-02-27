# Indian Horror Movies Finder (2000-2015)

This project strictly finds horror movies from Indian Wikipedia movie category pages and saves a CSV dataset.

It includes:
- All-India coverage via yearly `Indian films` category pages.
- Language-specific coverage (South and non-South categories).
- South Indian priority by default (`Tamil`, `Telugu`, `Malayalam`, `Kannada` first).
- Poster URL extraction from each movie's Wikipedia page.
- Description extraction from each movie page (first meaningful paragraph).
- Strict horror filtering (non-horror titles are dropped).
- Pause/resume support with checkpoint files.
- Parallel detail scraping for faster runs.
- Failed-task tracking with manual recovery tools.

## Features

- No API keys.
- No account authentication.
- Pure web scraping (`requests` + `BeautifulSoup`).
- CSV output with movie metadata.
- Resumable long runs.

## Output

Default output file:
- `indian_movies_2000_2015.csv`

CSV columns:
- `year`
- `language`
- `title`
- `movie_page_url`
- `poster_url`
- `description`
- `source_url`

## Supported Categories

Pan-India:
- `indian`

South India (default priority):
- `tamil`
- `telugu`
- `malayalam`
- `kannada`

North/Central India:
- `hindi`
- `punjabi`
- `bhojpuri`

West India:
- `marathi`
- `gujarati`

East/Northeast India:
- `bengali`
- `odia`
- `assamese`

## Requirements

- Python 3.x
- `requests`
- `beautifulsoup4`
- `lxml`

Install dependencies:

```bash
pip install -r requirements.txt
```

## Usage

Run with defaults (2000 to 2015, all configured sources, South-first order):

```bash
python3 horror_movies_scraper.py
```

Verbose progress logs:

```bash
python3 horror_movies_scraper.py --verbose
```

Custom year range:

```bash
python3 horror_movies_scraper.py --start-year 2005 --end-year 2010
```

Limit to specific sources:

```bash
python3 horror_movies_scraper.py --languages tamil telugu hindi indian
```

Disable South-first priority:

```bash
python3 horror_movies_scraper.py --no-prefer-south
```

Custom output/checkpoint files:

```bash
python3 horror_movies_scraper.py --output movies.csv --checkpoint progress.json
```

Faster run (parallel detail fetching + lower delay):

```bash
python3 horror_movies_scraper.py --workers 16 --request-delay 0.15 --verbose
```

## Pause and Resume

Pause automatically after N completed tasks:

```bash
python3 horror_movies_scraper.py --pause-after 5 --verbose
```

Resume from checkpoint:

```bash
python3 horror_movies_scraper.py --resume --checkpoint indian_movies_scrape_progress.json --verbose
```

If interrupted with `Ctrl+C`, progress is saved automatically and can be resumed.

## Checkpoint JSON Format

The checkpoint file (default: `indian_movies_scrape_progress.json`) stores scrape progress in JSON:

```json
{
  "version": 2,
  "config": {
    "start_year": 2000,
    "end_year": 2015,
    "languages": ["tamil", "telugu", "malayalam", "kannada", "indian"]
  },
  "completed_tasks": ["2000:tamil", "2000:telugu"],
  "failed_tasks": {
    "2001:indian": "404 Client Error: Not Found for url: ..."
  },
  "records": [
    {
      "year": 2000,
      "language": "tamil",
      "title": "Example Film",
      "movie_page_url": "https://en.wikipedia.org/wiki/Example_Film",
      "poster_url": "https://upload.wikimedia.org/...jpg",
      "description": "Example description text.",
      "source_url": "https://en.wikipedia.org/wiki/Category:2000_Tamil-language_films"
    }
  ],
  "movie_details_cache": {
    "https://en.wikipedia.org/wiki/Example_Film": {
      "poster_url": "https://upload.wikimedia.org/...jpg",
      "description": "Example description text."
    }
  }
}
```

Task id format used in JSON and CLI:
- `YEAR:LANGUAGE` (example: `2012:tamil`)

## Failed Tasks and Manual Recovery

The scraper writes failed tasks to:
- `failed_tasks.csv` (or your `--failed-report` path)

Retry only failed tasks from checkpoint:

```bash
python3 horror_movies_scraper.py --resume --failed-only --verbose
```

Mark tasks complete manually (skip them in future runs):

```bash
python3 horror_movies_scraper.py --resume --manual-complete-task 2008:tamil --manual-complete-task 2012:indian
```

Import manual records to help progress:

```bash
python3 horror_movies_scraper.py --resume --manual-records manual_records.csv
```

`manual_records.csv` must include columns:
- `year`
- `language`
- `title`
- `movie_page_url`
- `poster_url`
- `description`
- `source_url`

Tip:
- If a category task repeatedly fails, add key movies manually through `--manual-records`, then mark the task done with `--manual-complete-task YEAR:LANGUAGE`.

## Notes

- Wikipedia category coverage can vary by year/language.
- Missing category pages are skipped; the scraper continues.
- Poster URLs depend on Wikipedia infobox/image availability.
- Horror filtering is strict and uses page category labels, infobox genre, and description keywords.

## Files

- `horror_movies_scraper.py` - main scraper script
- `requirements.txt` - dependencies
- `MOVIE_DES.txt` - movie idea/description notes

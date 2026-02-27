# Indian Movies Scraper (2000-2015)

This project scrapes Indian movie titles from Wikipedia category pages and saves a CSV dataset.

It includes:
- All-India coverage via yearly `Indian films` category pages.
- Language-specific coverage (South and non-South categories).
- South Indian priority by default (`Tamil`, `Telugu`, `Malayalam`, `Kannada` first).
- Poster URL extraction from each movie's Wikipedia page.
- Description extraction from each movie page (first meaningful paragraph).
- Pause/resume support with checkpoint files.

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

## Supported Category Sources

- `indian`
- `tamil`
- `telugu`
- `malayalam`
- `kannada`
- `hindi`
- `bengali`
- `marathi`
- `punjabi`
- `gujarati`
- `odia`
- `assamese`
- `bhojpuri`

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

## Notes

- Wikipedia category coverage can vary by year/language.
- Missing category pages are skipped; the scraper continues.
- Poster URLs depend on Wikipedia infobox/image availability.

## Files

- `horror_movies_scraper.py` - main scraper script
- `requirements.txt` - dependencies
- `MOVIE_DES.txt` - movie idea/description notes

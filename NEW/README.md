# Indian Horror Movie Finder (IMDb Scraper + Viewer)

This project scrapes Indian horror feature movies from IMDb and saves data as JSON/CSV.
It also includes a simple HTML viewer with lazy-loaded poster images.

## Source URL

- `https://www.imdb.com/search/title/?title_type=feature&genres=horror&country_of_origin=IN`

## Setup

```bash
pip install -r requirements.txt
```

## Run Scraper

Default run:

```bash
python scraper.py
```

Useful options:

```bash
python scraper.py --max-pages 3 --sleep 1.0 --out-dir output
```

## Output Files

- `output/data/movies.json`
- `output/data/movies.csv`

## JSON Format Details

`movies.json` is an array of movie objects.

### JSON structure

```json
[
  {
    "imdb_id": "tt1234567",
    "title": "Movie Title",
    "year": 2020,
    "runtime": "2h 3m",
    "rating": 6.8,
    "votes": 15432,
    "genres": "Horror, Thriller",
    "imdb_url": "https://www.imdb.com/title/tt1234567/",
    "poster_url": "https://m.media-amazon.com/images/....jpg"
  }
]
```

### Field definitions

- `imdb_id` (`string`): IMDb title id like `tt1234567`
- `title` (`string`): movie title
- `year` (`number | null`): release year
- `runtime` (`string | null`): runtime text from IMDb
- `rating` (`number | null`): IMDb rating value
- `votes` (`number | null`): total vote count
- `genres` (`string | null`): comma-separated genres
- `imdb_url` (`string`): canonical IMDb title URL
- `poster_url` (`string | null`): direct poster image URL (image is not downloaded)

## HTML Viewer (Lazy Loading)

Viewer files are inside `viewer/`:

- `viewer/index.html`
- `viewer/styles.css`
- `viewer/app.js`

The viewer reads from `output/data/movies.json` and lazy-loads posters using `IntersectionObserver`.

Run a local server from project root:

```bash
python -m http.server 8000
```

Open:

- `http://localhost:8000/viewer/`

## Notes

- If scraping fails, IMDb may have changed markup or rate-limited requests.
- The scraper currently relies on CSS selectors from IMDb search result cards.

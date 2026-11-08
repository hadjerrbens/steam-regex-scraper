# steam-regex-scraper
# Steam Store Scraper (RegEx only)

Advanced Programming – Project 1: Web Data Collection Using Regular Expressions
3rd Year Engineering – Data Science, Abdelhamid Ibn Badis University, Mostaganem (2026–2027)

**Authors:** [Saffih Bouchra: Student 1,G2], [Bensaid Hadjer: Student 2,G1], [Dellali Fatima: Student 3,G1]
**Professor:** [Mr Zahmani]
**Website:** https://store.steampowered.com (public store pages)

## What it does

The script collects public information about video games from the Steam Store and saves it as a clean CSV file.
It works in two levels:

1. **Discovery:** it reads Steam search result pages (one query per genre) to get the list of games (app id, URL, title).
2. **Extraction:** it downloads each game page and pulls out the data with regular expressions.

Only `re`, `requests` and `csv` are used to read and organize the data.
No HTML parsing library (BeautifulSoup, Scrapy, lxml...) is used. The rest of the code uses the Python standard library.

## Requirements

- Python 3.10 or newer
- One extra package: `pip install requests`

## How to run

```bash
pip install requests
python scraper.py
```

The script runs the whole pipeline: discovery, download, extraction, cleaning, `data.csv`.
Pages are saved in a local `cache/` folder, so you can stop the script and start it again: it continues
where it stopped and does not download the same page twice. [TO FILL: confirm after the final merge]

Target size: up to 1,200 games, 200 per genre, for 10 genres (Action, RPG, Strategy, Adventure, Simulation,
Indie, Casual, Racing, Horror, Shooter). A full run takes roughly 30 minutes because of the delay between requests.

## Output files

| File | Content |
|---|---|
| `data.csv` | final cleaned dataset (the file to read) |
| `data/raw.csv` | the same games exactly as extracted, before cleaning |
| `stats.txt` | collection counts, % of filled values per column, top genres, games per year, prices |
| `logs/scrape.log` | every request with its URL, status and length |

## Columns of `data.csv`

One row per game. A missing value is an empty cell. Several values in one cell are separated by `;`.

| Column | Type | Meaning |
|---|---|---|
| app_id | integer | Steam id of the game (unique) |
| title | text | game name |
| url | text | `https://store.steampowered.com/app/<app_id>/` (tracking part removed) |
| developer, publisher | text | one or more names separated by `;` |
| release_date | text | ISO date `YYYY-MM-DD`, empty if "Coming soon" or not a real date |
| release_year | integer | year of release, kept even when the exact date is missing |
| price_final | decimal | current price in US dollars, `0.0` for free games, empty if no price yet |
| price_original | decimal | price before discount (equal to `price_final` when there is no discount) |
| discount_pct | integer | discount in percent, `0` if none |
| is_free | True/False | free to play or not |
| review_summary | text | Steam label, for example "Very Positive" |
| review_count | integer | number of user reviews |
| review_pct_positive | integer | percent of positive reviews |
| metacritic_score | integer | Metacritic score, only when the page shows one |
| genres | text | store genres separated by `;` ("Free To Play" is removed, see `is_free`) |
| categories | text | features such as Single-player, Steam Achievements |
| tags | text | first 5 user tags |
| platforms | text | `win`, `mac`, `linux` separated by `;` |
| description_short | text | short description, plain text on one line |
| dlc_count | integer | number of DLC listed on the page |

## How the data is cleaned

- HTML tags and entities (`&amp;`, `&quot;`, `&#39;`) are removed, including the double-encoded descriptions.
- Dates are converted to ISO format, and impossible dates (for example Feb 31) are rejected.
- Prices become numbers, counts with thousands separators (`174,873`) become integers, discounts (`-50%`) become `50`.
- Lists are split, trimmed and de-duplicated.
- Tracking parameters are removed from URLs.
- Rows are skipped, and counted in `stats.txt`, when the page is age-gated, the download failed, the app id is missing, or the game is a duplicate.
- A built-in `self_test()` checks every parser, and `validate()` prints the number of problems found in the final rows.

## Politeness and limits

- **Delay:** 1.5 seconds between real requests (cached pages are not downloaded again).
- **Errors:** timeouts, connection errors, 429 and 5xx answers are retried with a growing wait; after the last attempt the game is skipped.
- **No bypass:** verification pages and age-gated pages are detected, logged and skipped. The script does not try to get around them.
- **Language and region:** pages are requested in English with US prices (`cc=us`, `l=english`), so dates and currency look the same for every run.
- **Limitations:** the patterns depend on Steam's current HTML. If Steam changes its layout, some fields can become empty (see the coverage section of `stats.txt`). Only public store data is collected, at small scale, for a class project.

## Reading `data.csv`

The file is UTF-8 with a header row and comma-separated.
In Excel, do not double-click it (a French or Arabic Excel splits on `;` and shows one messy column). Use
**Data > From Text/CSV**, file origin **65001 UTF-8**, delimiter **Comma**.
With Python:

```python
import pandas as pd
df = pd.read_csv("data.csv", encoding="utf-8-sig")
print(df.head())
```

## Development layout (GitHub repository)

During development the code was split by member and merged into `scraper.py` at the end.

```
dev/a_fetch.py        fetching, cache, discovery, blocker detection (Member A)
dev/b_extract.py      regular expressions that read a game page (Member B)
dev/c_clean.py        cleaning, validation, CSV, statistics (Member C)
dev/make_raw_csv.py   builds data/raw.csv from saved pages, without internet
fixtures/             saved Steam pages used to test offline
```

Offline test with the saved pages:

```bash
python dev/make_raw_csv.py
python dev/c_clean.py
```

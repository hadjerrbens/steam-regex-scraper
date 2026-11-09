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

One row per game, 22 columns. A missing value is an empty cell. Several values in one cell are separated by `;`.

| Column | Type | Meaning |
|---|---|---|
| app_id | integer | Steam id of the game (unique) |
| title | text | game name |
| url | text | `https://store.steampowered.com/app/<app_id>/` (tracking part removed) |
| developer, publisher | text | one or more names separated by `;` |
| release_date | text | ISO date `YYYY-MM-DD`, empty if "Coming soon" or not a real date |
| release_year | integer | year of release, kept even when the exact date is missing |
| price_final | decimal | current price in US dollars, `0.0` for free games, empty if no price yet |
| price_final_usd | text | current price exactly as shown on the store, with the dollar sign (`$9.99`, `Free To Play`) |
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

## Regular expressions used

All patterns are compiled once at the top of the code with `re.compile`, and each one has a comment in the script.

### Extraction: reading a game page

| Field | Pattern idea | Why |
|---|---|---|
| Title | `<div id="appHubAppName"...>(.*?)</div>` | Anchored on a stable id. Lazy match ends at the first `</div>`. |
| Release date | `<div class="date">(.*?)</div>` | The class appears once per page, including "Coming soon" dates. |
| Developer, publisher | `Developer:</div>\s*<div class="summary column"...>(.*?)</div>` | Anchored on the label text, because the publisher div has no id. |
| Link names | `<a\b[^>]*>([^<]+)</a>` with `findall` | Keeps every name when a game has several. `\b` skips `<abbr>`. `[^<]+` keeps tags out of the CSV. |
| Genres | `<b>Genre:</b>(.*?)<br>` | Takes the genre line, then reads the link names inside it. |
| Description | `<meta name="Description" content="([^"]*)"` | A standard meta tag. `[^"]*` stops at the closing quote. |
| User tags | `<a\b[^>]*class="app_tag"[^>]*>(.*?)</a>` | The "+" button is a div with a different class, so it is skipped. |
| Price | `game_purchase_action_bg` up to `btn_addtocart`, then small patterns for the discount percent, the original price and the final price | Cutting out the first buy box first means bundle and DLC prices are never read. |
| Reviews | Row heading, then `(?:(?!</a>).)*?`, then label span, then `\((\d+)% of ([\d,]+)\)` | The tempered dot cannot cross `</a>`, so it stays inside one review row. Three named groups: label, pct, count. |
| Metascore | `id="game_area_metascore">\s*<div class="score \w+">\s*(\d+)` | `\w+` accepts high, medium and low. |
| Platforms | `platform_img (win\|mac\|linux)` | The alternation allows only the three known values. |
| Categories | `<div class="label">([^<]+)</div></a>` | Reads the label that ends each feature link. |
| DLC count | `Content For This Game.*?Browse all\s*<em>\((\d+)\)` | Reads the number in the DLC section header. |
| Age gate | `use_age_gate&quot;:\s*(?:true\|[1-9])` | Page JSON is HTML-escaped. `null` and `0` do not match. |

### Cleaning: turning the raw text into typed values

| Purpose | Pattern | Why |
|---|---|---|
| Leftover HTML tags | `<[^<>]*>` | `[^<>]*` cannot cross a `<` or `>`, so a match is never longer than one tag. |
| HTML entities | `&(#x[0-9a-fA-F]+\|#\d+\|[A-Za-z]+);` | Named (`&amp;`), decimal (`&#39;`) or hex entities; the `;` closes the match. |
| URL tracking part | `[?#].*$` | From the first `?` or `#` to the end of the URL. |
| Date, month first | `^([A-Za-z]{3})\w*\.?\s+(\d{1,2}),?\s+(\d{4})$` | Steam's `Apr 18, 2011`; `\w*` also accepts `April`. |
| Date, day first | `^(\d{1,2})\s+([A-Za-z]{3})\w*\.?,?\s+(\d{4})$` | The `18 Apr, 2011` order, in case a page uses it. |
| Year only | `\b(?:19\|20)\d{2}\b` | Keeps the year of texts like `Q4 2026` when there is no exact date. |
| Price amount | `\d[\d,]*\.?\d*` | First number of a price text, with thousands commas and decimals. |
| Non-digits | `\D` | Removing them turns `174,873` or `-50%` into a plain integer. |
| Yes / no words | `^(?:true\|1\|yes)$` and `^(?:false\|0\|no)$` | Whole cell only; accepts both teammates' formats, any case. |
| Free genre | `^free\s+to\s+play$` | Drops the genre item "Free To Play", already stored in `is_free`. |
| Word "free" | `\bfree\b` | Marks a price text as free; `\b` stops "freedom" from matching. |
| Leftovers check | `&#?\w+;\|<[^<>]+>` | Used by `validate()` to count tags or entities that survived cleaning. |

## How the data is cleaned

- HTML tags and entities (`&amp;`, `&quot;`, `&#39;`) are removed, including the double-encoded descriptions.
- Dates are converted to ISO format, and impossible dates (for example Feb 31) are rejected.
- Prices become numbers (the text as shown is also kept in `price_final_usd`), counts with thousands separators (`174,873`) become integers, discounts (`-50%`) become `50`.
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
fixtures/             saved Steam pages used to test offline
```

Offline test with the saved pages:

```bash
python dev/make_raw_csv.py
python dev/c_clean.py
```

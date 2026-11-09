
# Steam Regex Scraper
## Steam Store Scraper (Regular Expressions Only)

**Advanced Programming – Project 1: Web Data Collection Using Regular Expressions**

3rd Year Engineering – Data Science  
Abdelhamid Ibn Badis University of Mostaganem  
Academic Year: 2026–2027

**Authors:**
- Saffih Bouchra — Student 1, G2
- Bensaid Hadjer — Student 2, G1
- Dellali Fatima — Student 3, G1

**Professor:** Mr. Zahmani  
**Website:** https://store.steampowered.com

---

## 1. Project Overview

This project collects publicly available information about video games from the Steam Store and stores the extracted information in CSV files.

The scraper works in two main stages:

1. **Discovery:** Searches Steam Store pages by genre and collects game identifiers, URLs, and titles.
2. **Extraction:** Downloads individual game pages and extracts relevant information using regular expressions.

The project uses Python's `requests`, `re`, and `csv` modules for HTTP requests, HTML extraction, and CSV processing. Other Python standard-library modules support caching, logging, file handling, and execution.

No HTML parsing libraries such as BeautifulSoup, Scrapy, or lxml are used.

## 2. Requirements

- Python 3.10 or newer
- `requests`

Install the dependency:

```bash
pip install requests
```

## 3. How to Run

From the project root directory:

```bash
python main.py
```

The script runs the complete pipeline:

1. Discover games from Steam search pages.
2. Download individual game pages.
3. Extract information using regular expressions.
4. Clean and validate the extracted data.
5. Generate the final CSV dataset and statistics.

The scraper uses a local cache to avoid repeatedly downloading pages that have already been successfully collected. It also supports resuming interrupted runs.

## 4. Target Dataset

The project targets up to 1,200 games across ten genres, with a target of approximately 200 games per genre.

The genres are:

- Action
- RPG
- Strategy
- Adventure
- Simulation
- Indie
- Casual
- Racing
- Horror
- Shooter

The final number of unique records depends on genre overlap, page availability, and successful extraction.

A full collection run may take approximately 30 minutes or longer, depending on the number of requests, retries, and network conditions.

## 5. Output Files

| File | Description |
|---|---|
| `data/dataset_clean.csv` | Final cleaned dataset, intended for analysis and submission |
| `data/raw.csv` | Extracted data before cleaning |
| `data/dataset_age_gated.csv` | Records identified as age-gated |
| `data/stats.txt` | Collection statistics and validation results |
| `logs/scrape.log` | Request and scraping logs |
| `cache/` | Locally cached HTML pages |

## 6. Dataset Description

The cleaned dataset contains up to 22 columns, with one row per unique game.

| Column | Type | Description |
|---|---|---|
| `app_id` | Integer | Unique Steam application ID |
| `title` | Text | Game title |
| `url` | Text | Clean Steam Store URL |
| `developer` | Text | Developer name(s) |
| `publisher` | Text | Publisher name(s) |
| `release_date` | Text | Release date in ISO format (`YYYY-MM-DD`) |
| `release_year` | Integer | Release year |
| `price_final` | Decimal | Current price in USD; 0.0 for free games |
| `price_final_usd` | Text | Price as displayed by Steam |
| `price_original` | Decimal | Original price before discount |
| `discount_pct` | Integer | Discount percentage |
| `is_free` | Boolean | Whether the game is free to play |
| `review_summary` | Text | Steam review label |
| `review_count` | Integer | Number of user reviews |
| `review_pct_positive` | Integer | Percentage of positive reviews |
| `metacritic_score` | Integer | Metacritic score, when available |
| `genres` | Text | Game genres separated by semicolons |
| `categories` | Text | Features such as Single-player and Steam Achievements |
| `tags` | Text | First five user tags |
| `platforms` | Text | Supported platforms: win, mac, linux |
| `description_short` | Text | Short game description |
| `dlc_count` | Integer | Number of listed DLC items |

Missing values are represented by empty CSV cells. Multiple values in one field are separated by semicolons.

## 7. Regular Expressions Used

Regular expressions are compiled once using `re.compile()` and are documented in the source code.

### 7.1 Extraction Patterns

| Field | Pattern idea | Purpose |
|---|---|---|
| Title | `<div id="appHubAppName"...>(.*?)</div>` | Extracts the game title using a stable HTML identifier |
| Release date | `<div class="date">(.*?)</div>` | Extracts the displayed release date |
| Developer and publisher | `Developer:</div>\s*<div class="summary column"...>(.*?)</div>` | Locates developer and publisher information |
| Link names | `<a\b[^>]*>([^<]+)</a>` | Extracts text from links |
| Genres | `<b>Genre:</b>(.*?)<br>` | Isolates the genre section |
| Description | `<meta name="Description" content="([^"]*)"` | Extracts the short description |
| User tags | `<a\b[^>]*class="app_tag"[^>]*>(.*?)</a>` | Extracts user tags |
| Price | `game_purchase_action_bg` up to `btn_addtocart` | Isolates the purchase section before extracting prices |
| Reviews | Review-row pattern with a tempered dot | Extracts review label, positive percentage, and review count |
| Metascore | `id="game_area_metascore">\s*<div class="score \w+">\s*(\d+)` | Extracts the Metacritic score |
| Platforms | `platform_img (win\|mac\|linux)` | Identifies supported platforms |
| Categories | `<div class="label">([^<]+)</div></a>` | Extracts feature categories |
| DLC count | `Content For This Game.*?Browse all\s*<em>\((\d+)\)` | Extracts the listed DLC count |
| Age gate | `use_age_gate&quot;:\s*(?:true\|[1-9])` | Detects an age-gate indicator |

### 7.2 Cleaning Patterns

| Purpose | Pattern | Description |
|---|---|---|
| HTML tags | `<[^<>]*>` | Removes remaining HTML tags |
| HTML entities | `&(#x[0-9a-fA-F]+\|#\d+\|[A-Za-z]+);` | Identifies named, decimal, and hexadecimal entities |
| URL tracking | `[?#].*$` | Removes query parameters and fragments |
| Month-first date | `^([A-Za-z]{3})\w*\.?\s+(\d{1,2}),?\s+(\d{4})$` | Recognizes dates such as Apr 18, 2011 |
| Day-first date | `^(\d{1,2})\s+([A-Za-z]{3})\w*\.?,?\s+(\d{4})$` | Recognizes dates such as 18 Apr, 2011 |
| Year | `\b(?:19\|20)\d{2}\b` | Extracts a four-digit year |
| Price | `\d[\d,]*\.?\d*` | Extracts numeric price values |
| Non-digits | `\D` | Removes non-numeric characters when converting counts |
| Boolean values | `^(?:true\|1\|yes)$` and `^(?:false\|0\|no)$` | Recognizes common Boolean representations |
| Free genre | `^free\s+to\s+play$` | Identifies the Free To Play genre label |
| Free price | `\bfree\b` | Detects the word free |
| Leftover HTML | `&#?\w+;\|<[^<>]+>` | Detects HTML remnants during validation |

## 8. Data Cleaning and Validation

The cleaning stage transforms the extracted raw information into structured, consistent data.

The process includes:

- Removing HTML tags and decoding HTML entities.
- Normalizing dates into ISO format.
- Rejecting invalid calendar dates.
- Converting prices into numeric values.
- Converting review counts and discount percentages into integers.
- Normalizing Boolean values.
- Splitting, trimming, and deduplicating list fields.
- Removing tracking parameters from URLs.
- Removing duplicate games using their unique `app_id`.
- Separating age-gated records.
- Skipping records that cannot be processed successfully.
- Validating the final dataset and reporting missing or malformed values.

The project includes a `self_test()` function for parser testing and a `validate()` function for checking the cleaned dataset.

## 9. Politeness, Error Handling, and Limitations

### Request Politeness

- A delay of approximately 1.5 seconds is used between real requests.
- Cached pages are reused when possible.
- Timeouts and connection errors are handled.
- HTTP 429 and 5xx responses are retried with increasing wait times.

### Blocker Handling

The scraper detects verification pages and age-gated pages. These pages are logged and skipped rather than attempting to bypass access restrictions.

### Language and Region

Requests use English-language pages and US regional pricing (`cc=us`, `l=english`).

### Limitations

- Extraction patterns depend on Steam's current HTML structure.
- Changes to the Steam website may cause some fields to become empty.
- Some information may not be available for every game.
- Genre overlap can reduce the number of unique games discovered.
- Verification and age-gated pages may reduce the final dataset size.

The project collects publicly available store information for educational purposes.

## 10. Reading the Cleaned Dataset

The final dataset is UTF-8 encoded and comma-separated.

### Using Python

```python
import pandas as pd

df = pd.read_csv(
    "data/dataset_clean.csv",
    encoding="utf-8-sig"
)

print(df.head())
print(df.info())
```

### Using Excel

Use:

**Data → From Text/CSV**

- File origin: `65001 UTF-8`
- Delimiter: `Comma`

This avoids delimiter and encoding issues.

## 11. Project Structure

```text
steam-regex-scraper/
│
├── main.py
│
├── dev/
│   ├── a_fetch.py
│   ├── b_extract.py
│   └── c_clean.py
│
├── data/
│   ├── raw.csv
│   ├── dataset_clean.csv
│   ├── dataset_age_gated.csv
│   └── stats.txt
│
├── cache/
│
├── logs/
│   └── scrape.log
│
├── fixtures/
│
├── README.md
└── requirements.txt
```

The development code is organized by responsibility:

- `a_fetch.py`: Fetching, discovery, caching, and blocker detection (Member A).
- `b_extract.py`: Regular-expression extraction from Steam game pages (Member B).
- `c_clean.py`: Data cleaning, validation, CSV generation, and statistics (Member C).

## 12. Offline Testing

Saved HTML fixtures can be used to test extraction and cleaning without repeatedly requesting pages from Steam.

```bash
python dev/make_raw_csv.py
python dev/c_clean.py
```

These commands should be used when the corresponding fixture-generation script and test files are present.

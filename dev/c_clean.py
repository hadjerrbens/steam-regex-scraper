# This file cleans the game data collected from Steam.
# It saves the cleaned data in data/data.csv and the statistics in stats.txt.

import csv
import logging
import os
import re
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
RAW_CSV = DATA_DIR / "raw.csv"
DATA_CSV = DATA_DIR / "dataset_clean.csv"
AGE_GATED_CSV = DATA_DIR / "dataset_age_gated.csv"
STATS_TXT = ROOT / "stats.txt"
APP_URL = "https://store.steampowered.com/app/"

CLEAN_FIELDS = [
    "app_id", "title", "url", "developer", "publisher", "release_date", "release_year",
    "price_final", "price_original", "discount_pct", "is_free",
    "review_summary", "review_count", "review_pct_positive", "metacritic_score",
    "genres", "categories", "tags", "platforms", "description_short", "dlc_count","price_final_usd",
]


# Patterns used to find HTML tags, dates, prices and other values.

# Remove HTML tags and change HTML codes into normal characters
TAG_RE = re.compile(r"<[^<>]*>")
# Remove HTML codes such as &amp; and &#39; and change them into normal characters.
ENTITY_RE = re.compile(r"&(#x[0-9a-fA-F]+|#\d+|[A-Za-z]+);")
# Remove the query string and fragment from a URL.
QUERY_RE = re.compile(r"[?#].*$")
# Match dates in MM/DD/YYYY format.
DATE_MDY_RE = re.compile(r"^([A-Za-z]{3})\w*\.?\s+(\d{1,2}),?\s+(\d{4})$")
# Match dates in DD/MM/YYYY format.
DATE_DMY_RE = re.compile(r"^(\d{1,2})\s+([A-Za-z]{3})\w*\.?,?\s+(\d{4})$")
# Match years.
YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
# Match monetary amounts.
AMOUNT_RE = re.compile(r"\d[\d,]*\.?\d*")
# Match non-digit characters.
NON_DIGIT_RE = re.compile(r"\D")
# Match common yes/no values.
TRUE_RE = re.compile(r"^(?:true|1|yes)$", re.I)
# Match common no/false values.
FALSE_RE = re.compile(r"^(?:false|0|no)$", re.I)
# Match common free values.
GENRE_NOISE_RE = re.compile(r"^free\s+to\s+play$", re.I)
# Match common free values.
FREE_RE = re.compile(r"\bfree\b", re.I)
# Match leftover HTML codes or tags in the text.
LEFTOVER_RE = re.compile(r"&#?\w+;|<[^<>]+>")


# Some HTML codes need to be changed back into normal characters.
ENTITIES = {
    "amp": "&", "lt": "<", "gt": ">", "quot": '"', "apos": "'", "nbsp": " ",
    "ndash": "-", "mdash": "-", "hellip": "...", "trade": "TM", "reg": "(R)", "copy": "(c)",
    "lsquo": "'", "rsquo": "'", "ldquo": '"', "rdquo": '"',
}

# Month names are changed into numbers when reading dates.
MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
CORE_FIELDS = ["title", "developer", "publisher", "release_date", "genres", "price_final", "review_pct_positive"]

# Remove extra spaces and line breaks.

def collapse(text):
    return " ".join(text.split())

# Convert an HTML code such as &amp; into its character.

def entity_to_char(match):
    name = match.group(1)
    try:
        if name.startswith("#x"):
            return chr(int(name[2:], 16))
        if name.startswith("#"):
            return chr(int(name[1:]))
    except (ValueError, OverflowError):
        return match.group(0)
    return ENTITIES.get(name, match.group(0))

# Remove HTML tags and clean the text.

def clean_text(value, passes=1):
    if value is None:
        return ""
    # Remove tags before changing HTML codes into normal text.
    text = TAG_RE.sub(" ", str(value))
    # Some descriptions are encoded more than once.
    for _ in range(passes):
        text = ENTITY_RE.sub(entity_to_char, text)
    return collapse(TAG_RE.sub(" ", text))

# Remove tracking information from a URL.

def clean_url(value, app_id):
    text = QUERY_RE.sub("", clean_text(value))
    if text == "":
        return APP_URL + str(app_id) + "/"
    return text

# Clean a list separated by semicolons and remove duplicates.

def split_items(value, drop_free=False):
    text = clean_text(value)
    if text == "":
        return ""
    items = []
    # Split the values, clean each part, and keep unique items.
    for part in text.split(";"):
        part = collapse(part)
        if part == "":
            continue
        if drop_free and GENRE_NOISE_RE.match(part):
            continue
        if part not in items:
            items.append(part)
    return ";".join(items)

# Keep only the digits and convert the result to an integer.

def to_int(value):
    digits = NON_DIGIT_RE.sub("", clean_text(value))
    if digits == "":
        return ""
    return int(digits)

# Convert common yes/no values into True or False.

def to_bool(value):
    text = clean_text(value)
    if TRUE_RE.match(text):
        return True
    if FALSE_RE.match(text):
        return False
    return ""

# Convert a price into a number. Free games get price 0.

def parse_money(value):
    text = clean_text(value)
    if text == "":
        return ""
    if FREE_RE.search(text):
        return 0.0
    match = AMOUNT_RE.search(text)
    if not match:
        return ""
    return float(match.group(0).replace(",", ""))

# Check if the year has 366 days.

def is_leap(year):
    return (year % 4 == 0 and year % 100 != 0) or year % 400 == 0

# Get the number of days in a month.

def days_in_month(year, month):
    if month == 2 and is_leap(year):
        return 29
    return DAYS_IN_MONTH[month - 1]

# Read the date and return its date and year.

def parse_date(value):
    text = clean_text(value)
    match = DATE_MDY_RE.match(text)
    if match:
        month_name, day, year = match.groups()
    else:
        match = DATE_DMY_RE.match(text)
        if match:
            day, month_name, year = match.groups()
        else:
            found = YEAR_RE.search(text)
            if found:
                return "", int(found.group(0))
            return "", ""
    month = MONTHS.get(month_name.lower())
    year = int(year)
    day = int(day)
    # Check that the month and day make a real date.
    if month is None or day < 1 or day > days_in_month(year, month):
        return "", year
    return "%04d-%02d-%02d" % (year, month, day), year

# Clean all the values of one game.

def clean_record(raw):
    # The app ID is required to identify each game.
    app_id = int(clean_text(raw.get("app_id")))
    release_date, release_year = parse_date(raw.get("release_date"))
    price_final = parse_money(raw.get("price_final"))
    price_final_usd = clean_text(raw.get("price_final"))
    price_final = parse_money(price_final_usd)
    price_original = parse_money(raw.get("price_original"))
    # If there is no original price, use the final price.
    if price_original == "":
        price_original = price_final
    discount = to_int(raw.get("discount_pct"))
    if discount == "":
        discount = 0
    is_free = to_bool(raw.get("is_free"))
    # If the free status is missing, use the final price to find it.
    if is_free == "" and price_final != "":
        is_free = (price_final == 0.0)
    return {
        "app_id": app_id,
        "title": clean_text(raw.get("title")),
        "url": clean_url(raw.get("url"), app_id),
        "developer": split_items(raw.get("developer")),
        "publisher": split_items(raw.get("publisher")),
        "release_date": release_date,
        "release_year": release_year,
        "price_final": price_final,
        "price_final_usd": price_final_usd,
        "price_original": price_original,
        "discount_pct": discount,
        "is_free": is_free,
        "review_summary": clean_text(raw.get("review_summary")),
        "review_count": to_int(raw.get("review_count")),
        "review_pct_positive": to_int(raw.get("review_pct_positive")),
        "metacritic_score": to_int(raw.get("metacritic_score")),
        "genres": split_items(raw.get("genres"), drop_free=True),
        "categories": split_items(raw.get("categories")),
        "tags": split_items(raw.get("tags")),
        "platforms": split_items(raw.get("platforms")).lower(),
        "description_short": clean_text(raw.get("description_short"), passes=2),
        "dlc_count": to_int(raw.get("dlc_count")),
    }

# Keep only the first row for each app ID.

def dedupe(rows):
    seen = set()
    unique = []
    for row in rows:
        if row["app_id"] in seen:
            continue
        seen.add(row["app_id"])
        unique.append(row)
    return unique

# Check the cleaned rows and count possible problems.

def validate(rows):
    problems = Counter()
    for row in rows:
        for key in CORE_FIELDS:
            if row[key] == "":
                problems["empty " + key] += 1
        if row["price_final"] != "" and row["price_final"] < 0:
            problems["negative price"] += 1
        if row["price_final"] == 0.0 and row["is_free"] is not True:
            problems["price 0 but not free"] += 1
        if row["price_final"] != "" and row["price_original"] != "":
            if row["price_original"] < row["price_final"]:
                problems["original price below final price"] += 1
        for key in ("review_pct_positive", "discount_pct", "metacritic_score"):
            if row[key] != "" and (row[key] < 0 or row[key] > 100):
                problems[key + " outside 0-100"] += 1
        if LEFTOVER_RE.search(row["title"] + " " + row["description_short"]):
            problems["leftover tag or entity"] += 1
        if row["release_date"] != "" and (len(row["release_date"]) != 10 or row["release_date"][4] != "-"):
            problems["bad date format"] += 1
    print("validate: %d rows" % len(rows))
    if not problems:
        print("  no problem found")
    for key in sorted(problems):
        print("  %-36s %5d  (%.1f%%)" % (key, problems[key], 100.0 * problems[key] / max(len(rows), 1)))
    return problems

# Save the cleaned rows in a CSV file.

def save_csv(rows, path, fieldnames):
    os.makedirs(os.path.dirname(str(path)) or ".", exist_ok=True)
    # utf-8-sig helps Excel display special characters correctly.
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

# Calculate basic statistics and write them to stats.txt.

def summarize(rows, counts, path=STATS_TXT):
    genres = Counter()
    years = Counter()
    free = paid = unknown = 0
    price_sum = 0.0
    pct_sum = 0
    pct_n = 0
    for row in rows:
        for genre in row["genres"].split(";"):
            if genre != "":
                genres[genre] += 1
        if row["release_year"] != "":
            years[row["release_year"]] += 1
        if row["is_free"] is True:
            free += 1
        elif row["is_free"] is False and row["price_final"] != "":
            paid += 1
            price_sum += row["price_final"]
        else:
            unknown += 1
        if row["review_pct_positive"] != "":
            pct_sum += row["review_pct_positive"]
            pct_n += 1
    lines = ["COLLECTION"]
    for key in sorted(counts):
        lines.append("  %-34s %d" % (key, counts[key]))
    lines.append("  %-34s %d" % ("rows in data.csv", len(rows)))
    lines.append("")
    lines.append("COVERAGE (% of rows with a value)")
    for field in CLEAN_FIELDS:
        filled = 0
        for row in rows:
            if row[field] != "":
                filled += 1
        lines.append("  %-22s %5.1f%%" % (field, 100.0 * filled / max(len(rows), 1)))
    lines.append("")
    lines.append("PRICES")
    lines.append("  free: %d   paid: %d   no price yet: %d" % (free, paid, unknown))
    if paid > 0:
        lines.append("  average paid price: %.2f USD" % (price_sum / paid))
    if pct_n > 0:
        lines.append("  average positive reviews: %.1f%%" % (pct_sum / pct_n))
    lines.append("")
    lines.append("TOP GENRES")
    for genre, number in genres.most_common(10):
        lines.append("  %-24s %d" % (genre, number))
    lines.append("")
    lines.append("GAMES PER RELEASE YEAR")
    for year in sorted(years):
        lines.append("  %s  %d" % (year, years[year]))
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")

# Read the raw file, clean the data, and save the results.

def run(raw_path=RAW_CSV, out_path=DATA_CSV, stats_path=STATS_TXT):
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if not Path(raw_path).exists():
        raise SystemExit("Input not found: %s (run the crawl, or python dev/make_raw_csv.py)" % raw_path)
    # Read all rows from the raw CSV file.
    with open(raw_path, newline="", encoding="utf-8-sig") as handle:
        raw_rows = list(csv.DictReader(handle))
    counts = Counter()
    clean_rows = []
    age_gated_titles = []
    for raw in raw_rows:
        counts["raw rows read"] += 1
        status = clean_text(raw.get("fetch_status")).lower()
        if to_bool(raw.get("age_gate")) is True or status == "age_gate":
            counts["age-gated pages skipped"] += 1
            title = clean_text(raw.get("title"))
            if title:
                age_gated_titles.append({"title": title})
            continue
        if status not in ("", "ok"):
            counts["failed pages (" + status + ")"] += 1
            continue
        try:
            record = clean_record(raw)
        except (KeyError, ValueError) as error:
            counts["unusable rows (no app_id)"] += 1
            logging.warning("row skipped: %s | %s", raw.get("app_id"), error)
            continue
        if record["title"] == "":
            counts["rows without title"] += 1
            continue
        clean_rows.append(record)
    # Remove games that appear more than once.
    unique = dedupe(clean_rows)
    save_csv(age_gated_titles, AGE_GATED_CSV, ["title"])
    counts["duplicates removed"] = len(clean_rows) - len(unique)
    # Save the cleaned data, then check it and create the statistics.
    save_csv(unique, out_path, CLEAN_FIELDS)
    for key in sorted(counts):
        print("%-34s %d" % (key, counts[key]))
    validate(unique)
    summarize(unique, counts, stats_path)
    print("written: %s and %s" % (out_path, stats_path))
    return unique



# Test the main cleaning functions with sample values.

def self_test():
    assert parse_date("Apr 18, 2011") == ("2011-04-18", 2011)
    assert parse_date("18 Apr, 2011") == ("2011-04-18", 2011)
    assert parse_date("Feb 29, 2024") == ("2024-02-29", 2024)
    assert parse_date("Feb 31, 2020") == ("", 2020)
    assert parse_date("Coming soon") == ("", "") and parse_date(None) == ("", "")
    assert parse_date("Q4 2026") == ("", 2026)
    assert parse_money("$9.99") == 9.99 and parse_money("$1,299.99") == 1299.99
    assert parse_money("Free To Play") == 0.0 and parse_money("") == "" and parse_money(None) == ""
    assert to_int("174,873") == 174873 and to_int("-50%") == 50 and to_int(None) == "" and to_int(98) == 98
    assert to_bool("True") is True and to_bool("no") is False and to_bool("1") is True and to_bool(None) == ""
    assert split_items("Action;RPG") == "Action;RPG" and split_items("Action; RPG ;;Action") == "Action;RPG"
    assert split_items("Valve &amp; Co;Foo") == "Valve & Co;Foo"
    assert split_items("Action;Free to Play;RPG", drop_free=True) == "Action;RPG"
    assert clean_text("<em>Tom &amp; Jerry</em>\n  &#39;s") == "Tom & Jerry 's"
    assert clean_text("A &amp;quot;great&amp;quot; game", passes=2) == 'A "great" game'
    assert clean_text("&amp;lt;br&amp;gt;Hi", passes=2) == "Hi"
    assert clean_url("https://x/app/1/Foo/?snr=1_7", 1) == "https://x/app/1/Foo/"
    assert clean_url(None, 620) == APP_URL + "620/"
    discounted = {"app_id": "620", "title": "Portal &amp; 2", "url": None, "developer": "Valve", "publisher": "Valve",
                  "release_date": "Apr 18, 2011", "price_final": "$4.99", "price_original": "$9.99",
                  "discount_pct": "-50%", "is_free": "False", "review_summary": "Overwhelmingly Positive",
                  "review_count": "174,873", "review_pct_positive": "98", "metacritic_score": "95",
                  "genres": "Action;Adventure", "categories": "Single-player;Co-op", "platforms": "win;mac;linux",
                  "description_short": "A &amp;quot;great&amp;quot; game", "dlc_count": "2", "age_gate": "0",
                  "fetch_status": None, "tags": "Puzzle;Co-op"}
    row = clean_record(discounted)
    assert list(row.keys()) == CLEAN_FIELDS
    assert (row["app_id"], row["title"], row["release_date"], row["url"]) == (620, "Portal & 2", "2011-04-18", APP_URL + "620/")
    assert (row["price_final"], row["price_original"], row["discount_pct"], row["is_free"]) == (4.99, 9.99, 50, False)
    assert (row["review_count"], row["review_pct_positive"], row["description_short"]) == (174873, 98, 'A "great" game')
    free = clean_record({"app_id": "730", "price_final": "Free To Play", "is_free": "yes",
                         "genres": "Action; Free To Play", "release_date": "Aug 21, 2012"})
    assert (free["price_final"], free["price_original"], free["is_free"], free["genres"]) == (0.0, 0.0, True, "Action")
    empty = clean_record({"app_id": "1"})
    assert empty["title"] == "" and empty["price_final"] == "" and empty["discount_pct"] == 0 and empty["is_free"] == ""
    print("self-test OK")



if __name__ == "__main__":
    self_test()
    if RAW_CSV.exists():
        run()
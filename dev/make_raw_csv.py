"""Build data/raw.csv from saved app pages (no internet): fixtures/ or A's cache/ folder.
Uses B's extract_app_page, so the columns are exactly RAW_FIELDS (+ tags, like A's RAW_FIELDS).
    python dev/make_raw_csv.py              (cache/ if it has pages, else fixtures/)
    python dev/make_raw_csv.py fixtures     (a given folder)
    python dev/make_raw_csv.py --force      (overwrite an existing data/raw.csv)"""

import csv
import re
import sys
from pathlib import Path

from b_extract import RAW_FIELDS, extract_app_page, get_tags

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "raw.csv"
APP_URL = "https://store.steampowered.com/app/"      # same value as a_fetch.APP_URL
COLUMNS = list(RAW_FIELDS)
if "tags" not in COLUMNS:
    COLUMNS.append("tags")

# Ids of the fixtures A saved with make_fixtures.py (the other fixtures are read from the page itself).
KNOWN_IDS = {"app_paid": "620", "app_free": "730", "app_old": "70"}
# A's cache file name: cache/app_620.html -> group 1 = 620.
CACHE_NAME_RE = re.compile(r"^app_(\d+)\.html$")
# The page's canonical link: <link rel="canonical" href="https://store.steampowered.com/app/620/Portal_2/">.
CANONICAL_RE = re.compile(r'rel="canonical"\s+href="https?://store\.steampowered\.com/app/(\d+)/', re.I)


def find_app_id(path, html):
    """app id from the file name, then from the known fixtures, then from the canonical link."""
    named = CACHE_NAME_RE.match(path.name)
    if named:
        return named.group(1)
    if path.stem in KNOWN_IDS:
        return KNOWN_IDS[path.stem]
    link = CANONICAL_RE.search(html)
    if link:
        return link.group(1)
    return None


def build_rows(folder):
    """Read every app page of the folder and return a list of raw rows."""
    rows = []
    for path in sorted(folder.glob("*.html")):
        if path.name.startswith("search") or path.name.startswith("steam_test"):
            continue
        html = path.read_text(encoding="utf-8", errors="replace")
        app_id = find_app_id(path, html)
        if app_id is None:
            print("%-28s skipped (app id not found: add it to KNOWN_IDS)" % path.name)
            continue
        record = extract_app_page(html, app_id)
        if record["title"] is None:
            print("%-28s skipped (no title: not an app page)" % path.name)
            continue
        row = {}
        for field in COLUMNS:
            row[field] = record.get(field)
        row["tags"] = get_tags(html)
        row["url"] = APP_URL + app_id + "/"
        row["fetch_status"] = "ok"
        if record["age_gate"] == "1":          # same convention as A's crawl: skipped later by C
            row["age_gate"] = "yes"
            row["fetch_status"] = "age_gate"
        rows.append(row)
        print("%-28s id=%-8s %s" % (path.name, app_id, record["title"]))
    return rows


def main():
    args = sys.argv[1:]
    force = "--force" in args
    folders = []
    for arg in args:
        if arg != "--force":
            folders.append(Path(arg))
    if folders:
        folder = folders[0]
    elif list((ROOT / "cache").glob("app_*.html")):
        folder = ROOT / "cache"
    else:
        folder = ROOT / "fixtures"
    if OUT.exists() and not force:
        raise SystemExit("%s already exists (A's crawl?). Use --force to overwrite it." % OUT)
    rows = build_rows(folder)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print("%d rows written to %s (from %s)" % (len(rows), OUT, folder))


if __name__ == "__main__":
    main()
"""
names : bensaid hadjer
        saffih bouchra
        dellali fatima
website : steam store site https://store.steampowered.com/
description of data collected : games from 10 genres (Action, RPG, Strategy, Adventure,
Simulation, Indie, Casual, Racing, Horror, Shooter). 21 raw fields per game: title, developer,
publisher, release date, price (final, original, discount %, free flag), review summary, count
and % positive, metascore, genres, categories, platforms, short description, DLC count,
age-gate flag. raw.csv keeps values as found, data.csv is cleaned (ISO dates, numeric
prices, no HTML entities, no duplicates)

AI percentage: 65% 
and yes we understand it

"""
import csv

from a_fetch import (APP_PARAMS, APP_URL, DEFAULT_SEARCH_PARAMS, FIXTURE_DIR, ROOT, SEARCH_URL,
                     detect_blockers, fetch, setup_logging)

# name of the saved file -> Steam app id (the number in store.steampowered.com/app/<id>/)
APPS = {
    "app_paid": 620,            # Portal 2
    "app_free": 730,            # Counter-Strike 2
    "app_old": 70,              # Half-Life
    # Fill these in by browsing the store (see the explanation), then replace None with the app id:
    "app_discounted": None,     # a game with a -XX% badge right now
    "app_dlc": None,            # a DLC page (ask B; DLC is not in our search results)
    "app_unreleased": None,     # a "Coming soon" game
    "app_no_reviews": None,     # a tiny game that shows "No user reviews"
    "app_multi_dev": None,      # a game listing 2+ developers or publishers
    "app_age_gate": None,       # a mature game that asks for a birth date
}

PROTOTYPE_CSV = ROOT / "steam_games.csv"      # your first scraper's output (20 rows go to C)
SAMPLE_ROWS = 20


def save(name: str, html: str) -> None:
    """Write one fixture file as UTF-8."""
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    (FIXTURE_DIR / f"{name}.html").write_text(html, encoding="utf-8")


def main() -> None:
    setup_logging()

    # 1) one search-results page, exactly as the crawler receives it
    filters = {**DEFAULT_SEARCH_PARAMS, "tags": 19, "start": 0, "count": 50}
    html = fetch(SEARCH_URL, params=filters)
    if html:
        save("search_page", html)
        print(f"search_page.html           {detect_blockers(html):14} length={len(html)}")
    else:
        print("search_page.html           FAILED (see logs/scrape.log)")

    # 2) app pages
    for name, app_id in APPS.items():
        if app_id is None:
            print(f"{name + '.html':26} skipped (no app id yet)")
            continue
        html = fetch(f"{APP_URL}{app_id}/", params=APP_PARAMS)
        if html is None:
            print(f"{name + '.html':26} FAILED (see logs/scrape.log)")
            continue
        save(name, html)
        print(f"{name + '.html':26} {detect_blockers(html):14} length={len(html)}")

    # 3) raw_sample.csv for C: first rows of the prototype CSV
    if PROTOTYPE_CSV.exists():
        with open(PROTOTYPE_CSV, newline="", encoding="utf-8") as src:
            rows = list(csv.reader(src))[: SAMPLE_ROWS + 1]          # header + 20 rows
        with open(FIXTURE_DIR / "raw_sample.csv", "w", newline="", encoding="utf-8") as dst:
            csv.writer(dst).writerows(rows)
        print(f"raw_sample.csv             {len(rows) - 1} rows copied from {PROTOTYPE_CSV.name}")
    else:
        print(f"raw_sample.csv             {PROTOTYPE_CSV} not found: copy your prototype CSV there or edit PROTOTYPE_CSV")


if __name__ == "__main__":
    main()
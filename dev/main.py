from __future__ import annotations

import argparse
import csv
import importlib
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

ROOT = Path(__file__).resolve().parent
DEV_DIR = ROOT / "dev"
DATA_DIR = ROOT / "data"

RAW_CSV = DATA_DIR / "raw.csv"
CLEAN_CSV = DATA_DIR / "dataset_clean.csv"
AGE_GATED_CSV = DATA_DIR / "dataset_age_gated.csv"
FINAL_CSV = DATA_DIR / "data.csv"
SUMMARY_JSON = DATA_DIR / "run_summary.json"
STATS_TXT = ROOT / "stats.txt"
DISCOVERED_JSON = DATA_DIR / "discovered_games.json"

AGE_GATED_NOTE = "page served behind a birthdate check - not bypassed"


class ModuleUnavailable(RuntimeError):
    """A member's module could not be imported."""


def _load(module_name: str):
    """Import a member's module from dev/, with a clear message if it fails."""
    if str(DEV_DIR) not in sys.path:
        sys.path.insert(0, str(DEV_DIR))
    try:
        return importlib.import_module(module_name)
    except ImportError as error:
        if error.name == "requests":
            raise ModuleUnavailable(
                "Member A's module needs the 'requests' library:\n"
                "    pip install requests"
            ) from error
        raise ModuleUnavailable(
            "Could not import {0} from {1}:\n    {2}\n"
            "Is the file there? (it should be dev/{0}.py)".format(
                module_name, DEV_DIR, error)
        ) from error


# ---------------------------------------------------------------------------
# The three stages
# ---------------------------------------------------------------------------


def stage_discover(a_fetch, args) -> List[Dict[str, Any]]:
    """Stage 1 -- find the games on the search pages."""
    queries = None
    if args.genres:
        wanted = {name.strip().lower() for name in args.genres.split(",") if name.strip()}
        queries = [g for g in a_fetch.GENRES if g["name"].lower() in wanted]
        if not queries:
            raise SystemExit(
                "No known genre matched {0!r}. Known genres: {1}".format(
                    args.genres, ", ".join(g["name"] for g in a_fetch.GENRES)))
    games = a_fetch.discover_games(
        max_games=args.max_games,
        queries=queries,
        per_genre=args.per_genre,
        count=args.count,
    )
    if args.limit and len(games) > args.limit:
        games = games[:args.limit]
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DISCOVERED_JSON.write_text(json.dumps(games, indent=2), encoding="utf-8")
    print("  discovery : {0} unique games -> {1}".format(len(games), DISCOVERED_JSON))
    return games


def stage_fetch(a_fetch, games, args) -> Dict[str, Any]:
    """Stage 2 -- download every game page and turn it into a row."""
    extract_app_page, extractor_name = a_fetch.load_extractor()
    print("  parser    : {0}".format(extractor_name))
    stats = a_fetch.crawl(
        games,
        extract_app_page,
        resume=not args.no_resume,
        refresh=args.refresh,
        out_path=RAW_CSV,
    )
    print("  fetch     : ok={0} age_gate={1} failed={2} resumed={3}".format(
        stats.get("ok"), stats.get("age_gate"), stats.get("failed"),
        stats.get("resumed")))
    publish_raw()
    print("  raw       : {0}".format(FINAL_CSV))
    return stats


def stage_clean(c_clean, args) -> Dict[str, Any]:
    """Stage 3 -- clean the raw rows.

    Member C has two possible entry points, so both are supported:

        clean_file(input, out_dir)   -> the summary dictionary
        run(raw_path, out_path, ...) -> the cleaned rows
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if hasattr(c_clean, "clean_file"):
        summary = c_clean.clean_file(
            RAW_CSV, DATA_DIR, drop_demo=args.drop_demo)
        print("  clean     : {0} rows".format(summary.get("clean_rows")))
    elif hasattr(c_clean, "run"):
        rows = c_clean.run(
            raw_path=RAW_CSV,
            out_path=CLEAN_CSV,
            stats_path=STATS_TXT,
        )
        summary = {"clean_rows": len(rows), "age_gated_rows": None}
        print("  clean     : {0} rows".format(len(rows)))
    else:
        raise SystemExit(
            "Member C's module has neither clean_file() nor run().")

    ensure_clean_csv()
    return summary


def ensure_clean_csv() -> bool:
    """Make sure the cleaned rows are in data/dataset_clean.csv.

    Member C writes the file itself, but it may give it another name, so
    the file it wrote is moved into place here. The project always ends
    up with the same names.
    """
    if CLEAN_CSV.exists():
        return True
    candidates = [p for p in sorted(DATA_DIR.glob("*.csv"))
                  if p.name not in (FINAL_CSV.name, AGE_GATED_CSV.name,
                                    RAW_CSV.name)]
    if not candidates:
        return False
    shutil.copyfile(candidates[-1], CLEAN_CSV)
    return True


def write_age_gated_file() -> int:
    """Put the age-gated games in their own file.

    Member C's version of the cleaning drops them, so this makes sure they
    are never lost: they are the games whose pages sit behind a birthdate
    check, and their titles are all we have (we did not go past the check).
    """
    if not RAW_CSV.exists():
        return 0
    with RAW_CSV.open("r", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    gated = []
    for row in rows:
        status = (row.get("fetch_status") or "").strip().lower()
        age = (row.get("age_gate") or "").strip().lower()
        if status == "age_gate" or age in ("yes", "1", "true"):
            gated.append(row)

    if not gated:
        return 0

    with AGE_GATED_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["app_id", "title", "url", "age_gate", "fetch_status",
                         "note"])
        for row in gated:
            writer.writerow([
                row.get("app_id", ""),
                row.get("title", ""),
                row.get("url", ""),
                "yes",
                row.get("fetch_status", "age_gate"),
                AGE_GATED_NOTE,
            ])
    return len(gated)


def genre_counts(games: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    """How many games per genre.

    Member A stores this under "genres" or under "found_in_genres"
    depending on the version, so both are read.
    """
    counts: Dict[str, int] = {}
    for game in games:
        names = game.get("found_in_genres") or game.get("genres") or ["unknown"]
        for name in names:
            counts[name] = counts.get(name, 0) + 1
    return counts


def write_summary(a_fetch, stats: Dict[str, Any],
                  games: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Write data/run_summary.json -- the numbers the report needs."""
    payload = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "delay_seconds": getattr(a_fetch, "DELAY", 1.5) if a_fetch else 1.5,
        "user_agent": getattr(a_fetch, "USER_AGENT", "") if a_fetch else "",
        "games_discovered": len(games),
        "games_per_genre": genre_counts(games),
        "stats": {k: v for k, v in stats.items() if k != "needs_fix"},
        "needs_fix_count": len(stats.get("needs_fix", []) or []),
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARY_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def publish_raw() -> bool:
    """data/raw.csv -> data/data.csv.

    `data/data.csv` holds the **raw** rows (the 21 fields as they came off
    the page); `data/dataset_clean.csv` holds the cleaned ones. Member C
    reads the raw file, so the two are never mixed up.
    """
    if not RAW_CSV.exists():
        return False
    shutil.copyfile(RAW_CSV, FINAL_CSV)
    return True


# ---------------------------------------------------------------------------
# The command line
# ---------------------------------------------------------------------------


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the whole Steam dataset pipeline "
                    "(discover -> fetch -> parse -> clean).")
    parser.add_argument("--stage", choices=["all", "discover", "fetch", "clean"],
                        default="all",
                        help="which stage to run: 'discover' only finds the "
                             "games, 'fetch' discovers and downloads them, "
                             "'clean' cleans the raw rows, 'all' does "
                             "everything (default: all)")
    parser.add_argument("--max-games", type=int, default=1200,
                        help="maximum number of unique games (default: %(default)s)")
    parser.add_argument("--limit", type=int, default=0,
                        help="only download the first N of the discovered games "
                             "(0 = no limit)")
    parser.add_argument("--per-genre", type=int, default=200,
                        help="games wanted per genre (default: %(default)s)")
    parser.add_argument("--genres", type=str, default="",
                        help="comma separated genre names (default: all of them)")
    parser.add_argument("--count", type=int, default=50,
                        help="results per search page (default: %(default)s)")
    parser.add_argument("--delay", type=float, default=0.0,
                        help="seconds between two requests "
                             "(default: the delay of the module)")
    parser.add_argument("--refresh", action="store_true",
                        help="download the pages again, ignoring the cache")
    parser.add_argument("--no-resume", action="store_true",
                        help="ignore data/raw.csv and start from scratch")
    parser.add_argument("--drop-demo", action="store_true",
                        help="also drop the demo listings when cleaning")
    parser.add_argument("--verbose", action="store_true", help="debug logging")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)

    # Member A is only needed for the stages that talk to Steam. The
    # cleaning stage works on data/raw.csv and needs no network at all.
    a_fetch = None
    try:
        a_fetch = _load("a_fetch")
    except ModuleUnavailable as error:
        if args.stage in ("all", "discover", "fetch"):
            raise SystemExit(str(error))
        print("  note      : {0}".format(error))

    if a_fetch is not None and args.delay:
        a_fetch.DELAY = args.delay

    print("=" * 68)
    print("STEAM DATASET PIPELINE")
    print("=" * 68)
    started = time.monotonic()

    if a_fetch is not None:
        a_fetch.setup_logging(verbose=args.verbose)

    # --- stage 1 + 2 ---------------------------------------------------
    games: List[Dict[str, Any]] = []
    stats: Dict[str, Any] = {}

    if args.stage in ("all", "discover", "fetch"):
        games = stage_discover(a_fetch, args)
        if args.stage == "discover":
            print("\nDone (discovery only) in {0:.1f}s".format(
                time.monotonic() - started))
            return 0
        stats = stage_fetch(a_fetch, games, args)

    # --- stage 3 -------------------------------------------------------
    if args.stage in ("all", "clean"):
        if not RAW_CSV.exists():
            raise SystemExit(
                "No raw rows found at {0}.\n"
                "Run the fetch stage first:  python3 main.py --stage fetch".format(
                    RAW_CSV))
        try:
            c_clean = _load("c_clean")
        except ModuleUnavailable as error:
            raise SystemExit(str(error))
        clean_summary = stage_clean(c_clean, args)
        gated = write_age_gated_file()
        if gated:
            print("  age-gated : {0} games -> {1}".format(gated, AGE_GATED_CSV))
        if publish_raw():
            print("  raw       : {0}".format(FINAL_CSV))
        stats.setdefault("clean_rows", clean_summary.get("clean_rows"))
        if clean_summary.get("age_gated_rows") is None:
            stats["age_gated_rows"] = gated

    if games:
        write_summary(a_fetch, stats, games)

    print("-" * 68)
    print("Done in {0:.1f}s".format(time.monotonic() - started))
    if stats:
        print("  {0}".format(json.dumps(
            {k: v for k, v in stats.items() if k != "needs_fix"})))
    return 0


if __name__ == "__main__":
    sys.exit(main())

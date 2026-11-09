from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import sys
from pathlib import Path
from types import ModuleType
from typing import Any


# ============================================================
# PROJECT PATHS
# ============================================================

ROOT = Path(__file__).resolve().parent
DEV_DIR = ROOT / "dev"
DATA_DIR = ROOT / "data"
CACHE_DIR = ROOT / "cache"
LOG_DIR = ROOT / "logs"
FIXTURE_DIR = ROOT / "fixtures"

RAW_CSV = DATA_DIR / "raw.csv"
CLEAN_CSV = DATA_DIR / "dataset_clean.csv"
AGE_GATED_CSV = DATA_DIR / "dataset_age_gated.csv"
STATS_TXT = DATA_DIR / "stats.txt"

DISCOVERED_JSON = DATA_DIR / "discovered_games.json"
RUN_SUMMARY_JSON = DATA_DIR / "run_summary.json"
NEEDS_FIX_TXT = DATA_DIR / "needs_fix.txt"


# ============================================================
# LOAD A PYTHON FILE FROM ITS PATH
# ============================================================

def load_module(file_path: Path, module_name: str) -> ModuleType:
    """
    Load a Python module from a specific file path.

    This allows main.py to receive the paths of the
    fetcher, parser, and cleaner as command-line arguments.
    """

    file_path = file_path.resolve()

    if not file_path.is_file():
        raise FileNotFoundError(
            f"Module file not found: {file_path}"
        )

    spec = importlib.util.spec_from_file_location(
        module_name,
        file_path
    )

    if spec is None or spec.loader is None:
        raise ImportError(
            f"Could not load module from: {file_path}"
        )

    module = importlib.util.module_from_spec(spec)

    # Register before execution so normal module imports work.
    sys.modules[module_name] = module

    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise

    return module


# ============================================================
# COMMAND-LINE ARGUMENTS
# ============================================================

def parse_args() -> argparse.Namespace:

    parser = argparse.ArgumentParser(
        description="Steam dataset pipeline: discovery, fetching, parsing and cleaning."
    )

    parser.add_argument(
        "--fetcher",
        type=Path,
        default=DEV_DIR / "a_fetch.py",
        help="Path to Member A's fetcher file."
    )

    parser.add_argument(
        "--parser",
        type=Path,
        default=DEV_DIR / "b_extract.py",
        help="Path to Member B's extraction file."
    )

    parser.add_argument(
        "--cleaner",
        type=Path,
        default=DEV_DIR / "c_clean.py",
        help="Path to Member C's cleaning file."
    )

    parser.add_argument(
        "--stage",
        choices=["all", "discover", "fetch", "clean"],
        default="all",
        help="Which pipeline stage to execute."
    )

    parser.add_argument(
        "--max-games",
        type=int,
        default=None,
        help="Maximum number of unique games to discover."
    )

    parser.add_argument(
        "--per-genre",
        type=int,
        default=None,
        help="Maximum number of games to collect per genre."
    )

    parser.add_argument(
        "--count",
        type=int,
        default=None,
        help="Number of search results requested per Steam page."
    )

    parser.add_argument(
        "--delay",
        type=float,
        default=None,
        help="Delay between requests, in seconds."
    )

    parser.add_argument(
        "--genres",
        type=str,
        default=None,
        help="Comma-separated genre names, e.g. Action,RPG,Strategy."
    )

    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Refresh cached HTML instead of reusing it."
    )

    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Do not reuse rows already present in raw.csv."
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable detailed logging."
    )

    return parser.parse_args()


# ============================================================
# PREPARE PROJECT DIRECTORIES
# ============================================================

def create_directories() -> None:

    for directory in (
            DATA_DIR,
            CACHE_DIR,
            LOG_DIR,
            FIXTURE_DIR
    ):
        directory.mkdir(parents=True, exist_ok=True)


# ============================================================
# LOAD THE THREE PROJECT MODULES
# ============================================================

def load_project_modules(
        args: argparse.Namespace
) -> tuple[ModuleType, ModuleType, ModuleType]:

    fetcher = load_module(
        args.fetcher,
        "project_a_fetch"
    )

    extractor = load_module(
        args.parser,
        "project_b_extract"
    )

    cleaner = load_module(
        args.cleaner,
        "project_c_clean"
    )

    # Check that each module exposes the function main.py needs.
    required_functions = {
        "fetcher": (
            fetcher,
            ("discover_games", "crawl", "setup_logging",
             "write_run_summary", "write_needs_fix")
        ),
        "extractor": (
            extractor,
            ("extract_app_page",)
        ),
        "cleaner": (
            cleaner,
            ("run",)
        ),
    }

    for module_label, (module, function_names) in required_functions.items():

        for function_name in function_names:

            if not callable(getattr(module, function_name, None)):
                raise AttributeError(
                    f"{module_label} module does not provide "
                    f"a callable '{function_name}()'."
                )

    return fetcher, extractor, cleaner


# ============================================================
# CONFIGURE THE MODULE PATHS
# ============================================================

def configure_paths(
        fetcher: ModuleType,
        cleaner: ModuleType
) -> None:

    # Member A's original ROOT uses the directory containing
    # a_fetch.py. Since that file is inside dev/, correct it
    # to point to the project root.

    fetcher.ROOT = ROOT
    fetcher.DEV_DIR = DEV_DIR
    fetcher.DATA_DIR = DATA_DIR
    fetcher.CACHE_DIR = CACHE_DIR
    fetcher.LOG_DIR = LOG_DIR
    fetcher.FIXTURE_DIR = FIXTURE_DIR
    fetcher.RAW_CSV = RAW_CSV

    # Member C already calculates ROOT using parent.parent,
    # but we explicitly align its output paths with this project.

    cleaner.ROOT = ROOT
    cleaner.DATA_DIR = DATA_DIR
    cleaner.RAW_CSV = RAW_CSV
    cleaner.DATA_CSV = CLEAN_CSV
    cleaner.AGE_GATED_CSV = AGE_GATED_CSV
    cleaner.STATS_TXT = STATS_TXT


# ============================================================
# CONFIGURE THE RAW CSV SCHEMA
# ============================================================

def configure_schema(
        fetcher: ModuleType,
        extractor: ModuleType
) -> None:

    # The parser owns the fields it extracts.
    # Use its schema for the CSV written by the fetcher.

    parser_fields = getattr(extractor, "RAW_FIELDS", None)

    if not parser_fields:
        raise AttributeError(
            "b_extract.py must define RAW_FIELDS."
        )

    fetcher.RAW_FIELDS = list(parser_fields)

    # The fetcher also stores the genre used during discovery.
    fetcher.RAW_COLUMNS = (
            list(fetcher.RAW_FIELDS)
            + ["found_in_genres"]
    )


# ============================================================
# APPLY COMMAND-LINE SETTINGS
# ============================================================

def configure_settings(
        args: argparse.Namespace,
        fetcher: ModuleType
) -> dict[str, Any]:

    max_games = (
        args.max_games
        if args.max_games is not None
        else fetcher.MAX_GAMES
    )

    per_genre = (
        args.per_genre
        if args.per_genre is not None
        else fetcher.PER_GENRE
    )

    count = (
        args.count
        if args.count is not None
        else fetcher.COUNT
    )

    if args.delay is not None:
        if args.delay < 0:
            raise ValueError("--delay cannot be negative.")

        fetcher.DELAY = args.delay

    if max_games < 1:
        raise ValueError("--max-games must be at least 1.")

    if per_genre < 1:
        raise ValueError("--per-genre must be at least 1.")

    if count < 1:
        raise ValueError("--count must be at least 1.")

    return {
        "max_games": max_games,
        "per_genre": per_genre,
        "count": count,
    }


# ============================================================
# SELECT GENRES
# ============================================================

def select_genres(
        fetcher: ModuleType,
        genres_argument: str | None
) -> list[dict[str, Any]]:

    available_genres = list(fetcher.GENRES)

    if not genres_argument:
        return available_genres

    requested_names = {
        name.strip().lower()
        for name in genres_argument.split(",")
        if name.strip()
    }

    selected = [
        genre
        for genre in available_genres
        if genre.get("name", "").lower() in requested_names
    ]

    found_names = {
        genre.get("name", "").lower()
        for genre in selected
    }

    unknown_names = requested_names - found_names

    if unknown_names:
        raise ValueError(
            "Unknown genre(s): "
            + ", ".join(sorted(unknown_names))
        )

    if not selected:
        raise ValueError("No genres were selected.")

    return selected


# ============================================================
# STAGE 1: DISCOVER GAMES
# ============================================================

def stage_discover(
        fetcher: ModuleType,
        settings: dict[str, Any],
        genres: list[dict[str, Any]]
) -> list[dict[str, Any]]:

    logging.info("Starting game discovery.")

    games = fetcher.discover_games(
        max_games=settings["max_games"],
        queries=genres,
        per_genre=settings["per_genre"],
        count=settings["count"]
    )

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    DISCOVERED_JSON.write_text(
        json.dumps(games, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    logging.info(
        "Discovery finished: %d unique games.",
        len(games)
    )

    logging.info(
        "Discovered games saved to: %s",
        DISCOVERED_JSON
    )

    return games


# ============================================================
# READ DISCOVERED GAMES
# ============================================================

def read_discovered_games() -> list[dict[str, Any]]:

    if not DISCOVERED_JSON.is_file():
        raise FileNotFoundError(
            f"{DISCOVERED_JSON} does not exist. "
            "Run main.py --stage discover first, "
            "or use --stage all."
        )

    with DISCOVERED_JSON.open(
            "r",
            encoding="utf-8"
    ) as file:
        games = json.load(file)

    if not isinstance(games, list):
        raise ValueError(
            "discovered_games.json must contain a list of games."
        )

    return games


# ============================================================
# STAGE 2: FETCH HTML AND EXTRACT DATA
# ============================================================

def stage_fetch(
        fetcher: ModuleType,
        extractor: ModuleType,
        games: list[dict[str, Any]],
        args: argparse.Namespace
) -> dict[str, Any]:

    logging.info("Starting fetching and extraction.")

    # Pass Member B's real extractor directly to Member A's crawl.
    # Do NOT use fetcher's fallback extractor.

    stats = fetcher.crawl(
        games=games,
        extract_app_page=extractor.extract_app_page,
        resume=not args.no_resume,
        refresh=args.refresh,
        out_path=RAW_CSV
    )

    # Save the reports in the project's data/ directory.

    fetcher.write_run_summary(
        stats,
        games,
        path=RUN_SUMMARY_JSON
    )

    fetcher.write_needs_fix(
        stats,
        path=NEEDS_FIX_TXT
    )

    logging.info("Fetching finished.")
    logging.info("Raw CSV: %s", RAW_CSV)

    return stats


# ============================================================
# STAGE 3: CLEAN DATA
# ============================================================

def stage_clean(cleaner: ModuleType) -> list[dict[str, Any]]:

    logging.info("Starting data cleaning.")

    if not RAW_CSV.is_file():
        raise FileNotFoundError(
            f"Raw CSV not found: {RAW_CSV}. "
            "Run the fetch stage first."
        )

    cleaned_rows = cleaner.run(
        raw_path=RAW_CSV,
        out_path=CLEAN_CSV,
        stats_path=STATS_TXT
    )

    logging.info(
        "Cleaning finished: %d cleaned rows.",
        len(cleaned_rows)
    )

    logging.info("Clean CSV: %s", CLEAN_CSV)
    logging.info("Statistics: %s", STATS_TXT)

    return cleaned_rows


# ============================================================
# MAIN PIPELINE
# ============================================================

def main() -> None:

    args = parse_args()

    create_directories()

    # Load the actual three files selected by the user.

    fetcher, extractor, cleaner = load_project_modules(args)

    # Fix the paths before running any stage.

    configure_paths(fetcher, cleaner)

    # Make the fetcher's CSV columns match the parser's fields.

    configure_schema(fetcher, extractor)

    # Set up logging using the project's logs/ directory.

    fetcher.setup_logging(
        log_dir=LOG_DIR,
        verbose=args.verbose
    )

    # Apply the settings after loading the fetcher,
    # so its own defaults can be used.

    settings = configure_settings(args, fetcher)

    genres = select_genres(
        fetcher,
        args.genres
    )

    logging.info("Pipeline stage: %s", args.stage)

    logging.info("Fetcher: %s", args.fetcher.resolve())
    logging.info("Parser: %s", args.parser.resolve())
    logging.info("Cleaner: %s", args.cleaner.resolve())

    if args.stage == "discover":

        stage_discover(
            fetcher,
            settings,
            genres
        )

    elif args.stage == "fetch":

        games = read_discovered_games()

        stage_fetch(
            fetcher,
            extractor,
            games,
            args
        )

    elif args.stage == "clean":

        stage_clean(cleaner)

    else:
        # Full pipeline: discover -> fetch/extract -> clean.

        games = stage_discover(
            fetcher,
            settings,
            genres
        )

        stage_fetch(
            fetcher,
            extractor,
            games,
            args
        )

        stage_clean(cleaner)

    logging.info("Pipeline completed successfully.")


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    try:
        main()

    except KeyboardInterrupt:
        print("\nPipeline interrupted by user.")
        raise SystemExit(130)

    except Exception as error:
        logging.exception("Pipeline failed: %s", error)
        raise SystemExit(1)
import json
import logging
import re
import sys
import time
from urllib.parse import unquote
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple, Sequence
import html as html_lib

import requests

ROOT = Path(__file__).resolve().parent.parent
DEV_DIR = ROOT / "dev"
CACHE_DIR = ROOT / "cache"
DATA_DIR = ROOT / "data"
LOG_DIR = ROOT / "logs"
FIXTURE_DIR = ROOT / "fixtures"
RAW_CSV = DATA_DIR / "raw.csv"

LOGGER = logging.getLogger("scrape")

BASE_URL = "https://store.steampowered.com"
SEARCH_URL = f"{BASE_URL}/search/"
APP_URL = f"{BASE_URL}/app/"

HEADERS = {
    "User-Agent": "ClassProject-RegexScraper/1.0",
    "Accept-Language": "en-US,en;q=0.9"
}
APP_PARAMS = {"cc": "us", "l": "english"}
DELAY=1.5
COUNT = 50
DEFAULT_SEARCH_PARAMS: Dict[str, Any] = {
    "category1": 998,#   category1=998 -> "Games" only (no DLC, no soundtracks, no demos)
    "ndl": 1,#   ndl=1         -> hide the "Downloadable Content" rows
    "ignore_preferences": 1,
}
RE_AGE_GATE = re.compile(
    r'"/agecheck'               #new SSR route for age-restricted apps
    r"|/parental/agecheck"      #the parental age-check endpoint
    r"|%2Fagecheck"             #URL-encoded, inside the sign-in redirect
    r'|"use_age_gate":\s*true'  #app JSON flag (only when it is really on)
    r"|age_gate_content"        #age-gate container
    r"|InitAgeGate",            #age-gate JS hook
    re.I,
)

RE_VERIFICATION = re.compile(
    r"verify (?:that )?you are (?:a )?human"
    r"|are you a robot"
    r"|unusual traffic"
    r"|checking your browser"
    r"|access denied"
    r"|request blocked"
    r"|too many requests"
    r"|<title>[^<]{0,80}?(?:Error 403|Access Denied|403 Forbidden|Forbidden)\s*</title>",
    re.I,
)
RE_TOTAL_RESULTS = re.compile(
    r"showing\s+[\d,]+\s*-\s*[\d,]+\s+of\s+(?P<paged>[\d,]+)"
    r'|class="search_results_count">\s*(?P<count>[\d,]+)\s+results',
    re.I,
)

RE_NO_MORE_RESULTS = re.compile(
    r'class="search_results_count">\s*0\s+results'
    r'|search_result_container"[^>]*>\s*(?:<div class="search_rule"></div>\s*)?</div>',
    re.I,
)

#markers that tell us the page really is the thing we asked for.
RE_APP_MARKER = re.compile(r"apphub_AppName|appHubAppName|valve-ssr-data", re.I)
RE_SEARCH_MARKER = re.compile(
    r"search_result_row|search_pagination|search_results_count", re.I
)

RE_SEARCH_ROW = re.compile(
    r'<a\b[^>]*\bclass="[^"]*\bsearch_result_row\b[^"]*"[^>]*>(?P<body>.*?)</a>',
    re.S | re.I,
    )

RE_APP_LINK = re.compile(
    r'href="(?P<url>https?://store\.steampowered\.com/app/(?P<app_id>\d+)/[^"]*)"',
    re.I,
)

RE_TITLE = re.compile(r'<span class="title">(?P<title>.*?)</span>', re.S | re.I)

GENRES: List[Dict[str, Any]] = [
    {"name": "Action", "tag": 19},
    {"name": "RPG", "tag": 122},
    {"name": "Strategy", "tag": 9},
    {"name": "Adventure", "tag": 21},
    {"name": "Simulation", "tag": 599},
    {"name": "Indie", "tag": 492},
    {"name": "Casual", "tag": 597},
    {"name": "Racing", "tag": 699},
    {"name": "Horror", "tag": 1667},
    {"name": "Shooter", "tag": 1774},
]
RAW_FIELDS: List[str] = [
    "app_id",
    "title",
    "url",
    "developer",
    "publisher",
    "release_date",
    "price_final",
    "price_original",
    "discount_pct",
    "is_free",
    "review_summary",
    "review_count",
    "review_pct_positive",
    "metacritic_score",
    "genres",
    "categories",
    "platforms",
    "description_short",
    "dlc_count",
    "age_gate",
    "fetch_status",
]
MAX_GAMES = 1200      # size of the final dataset
PER_GENRE = 200       # games wanted per genre
RAW_COLUMNS = list(RAW_FIELDS) + ["found_in_genres"]   # found_in_genres = genres we SEARCHED (not the page's genres)

def setup_logging(log_dir:Path = LOG_DIR,verbose:bool=False)-> logging.Logger:
    log_dir.mkdir(parents=True,exist_ok=True)
    LOGGER.setLevel(logging.DEBUG)
    LOGGER.handlers.clear()
    LOGGER.propagate = False

    fmt = logging.Formatter( "%(asctime)s | %(levelname)-7s | %(message)s", "%Y-%m-%d %H:%M:%S")
    file_handler = logging.FileHandler(log_dir/"scrape.log",encoding="utf-8")
    file_handler.setFormatter(fmt)
    file_handler.setLevel(logging.DEBUG)
    LOGGER.addHandler(file_handler)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    console.setLevel(logging.DEBUG if verbose else logging.INFO)
    LOGGER.addHandler(console)

    return LOGGER

def polite_sleep()-> None:
    time.sleep(DELAY)
BACKOFF_MAX = 60.0 #never wait longer than this between attempts
BACKOFF_BASE = 5.0 #seconds on every failed attempt
def backoff(attempt :int)->float:
    wait = BACKOFF_BASE * (2**max(0,attempt-1))
    return min(wait,BACKOFF_MAX)

def fetch(url, params=None, retries=3):
    for attempt in range(1, max(1, retries) + 1):
        polite_sleep()
        try:
            response = requests.get(
                url,
                headers=HEADERS,
                params=params,
                timeout=15
            )

        except requests.RequestException as error:
            LOGGER.warning("GET %s | request failed: %s | attempt %d/%d", url, error, attempt, retries)
        else:
            status = response.status_code
            length = len(response.text)
            if status == 200:
                if response.history:
                    LOGGER.info("GET %s |status = 200 | length = %d | redirected to %s",url,length,response.url)
                LOGGER.info("GET %s | status=200 | length=%d", url, length)
                return  response.text
            if status == 429 or 500 <= status < 600:
                wait = backoff(attempt)

                LOGGER.warning("GET %s | status=%d | length=%d | retrying in %.0fs "
                                   "(attempt %d/%d)", url, status, length, wait, attempt, retries)
                if attempt < retries:
                    time.sleep(wait)
                    continue
                LOGGER.error("GET %s | status=%d | giving up after %d attempts",
                             url, status, retries)
                return None
            LOGGER.error("GET %s | status=%d | length=%d | not retrying",
                         url, status, length)
            return None
        if attempt < retries:
            wait = backoff(attempt)
            LOGGER.info("GET %s | waiting %.0fs before retry", url, wait)
            time.sleep(wait)

    LOGGER.error("GET %s | exhausted %d attempts | returning None", url, retries)
    return None
def cached_get(url, name, params=None,refresh =False):
    CACHE_DIR.mkdir(parents=True,exist_ok=True)
    path = CACHE_DIR/f"{name}.html"
    if path.exists() and not refresh:
        try:
            html = path.read_text(encoding="utf-8", errors="replace")
            LOGGER.info("CACHE HIT | %s", path.name)
            return html
        except OSError as error:
            LOGGER.error("Cannot read cache %s: %s | fetching again", path, error)
    if refresh and path.exists():
        LOGGER.info("CACHE REFRESH | %s", path.name)
    else :
        LOGGER.info("CACHE MISS | %s", path.name)
    html  = fetch(url,params)
    if html is None:
        return None
    try:
        path.write_text(html, encoding="utf-8")
        LOGGER.info("CACHE WRITE | %s | length=%d", path.name, len(html))
    except OSError as error:
        LOGGER.error("Cannot write cache %s: %s", path, error)
    return html

def detect_blockers(html:Optional[str],url:Optional[str]=None):
    if html is None or not html.strip():
        return "empty"
    if url:
        if "/agecheck" in unquote(url):
            return "age_gate"
    if RE_AGE_GATE.search(html):
        return "age_gate"
    if RE_VERIFICATION.search(html):
        return "verification"
    if RE_NO_MORE_RESULTS.search(html) and not RE_SEARCH_ROW.search(html):
        return "empty"

    if RE_APP_MARKER.search(html) or RE_SEARCH_MARKER.search(html):
        return "ok"

    return "empty"

def _slug(text:str)->str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", str(text)).strip("-").lower() or "page"

def _read_fixture(name:str)->Optional[str]:
    path = Path(name)
    if not path.exists():
        candidate = FIXTURE_DIR / name
        if not candidate.exists():
            LOGGER.error("FIXTURE | %s not found", candidate)
            return None
        path = candidate
    LOGGER.info("FIXTURE | reading %s (no request sent)", path)
    return path.read_text(encoding="utf-8", errors="replace")

def _unwrap_search_response(html:str)->str:
    stripped = html.lstrip()
    if not stripped.startswith("{"):
        return html
    try:
        payload = json.loads(stripped)
    except ValueError:
        return html
    if isinstance(payload, dict) and isinstance(payload.get("results_html"), str):
        LOGGER.info("UNWRAP | the site answered with the JSON search envelope")
        return payload["results_html"]
    return html

def _search_page(start:int,count:int =COUNT,filters:Optional[Dict[str,Any]]=None,fixture:Optional[str]=None)->Tuple[List[Dict[str,Any]],Optional[str]]:
    filters = dict(filters or DEFAULT_SEARCH_PARAMS)
    filters["start"] = start
    filters["count"] = count

    name ="search_{}_{}".format(_slug("_".join(f"{k}{v}" for k,v in sorted(filters.items()) if k not in ("start","count"))),start)
    if fixture:
        html = _read_fixture(fixture)
    else:
        html = cached_get(SEARCH_URL, name, params=filters)
    if html is None:
        return [], None
    html = _unwrap_search_response(html)
    rows: List[Dict[str, Any]] = []
    for match in RE_SEARCH_ROW.finditer(html):
        block = match.group(0)
        link = RE_APP_LINK.search(block)
        if not link:
            continue
        app_id = link.group("app_id")
        title_match = RE_TITLE.search(block)
        title = ""
        if title_match:
            title = html_lib.unescape(title_match.group("title")).strip()
        rows.append(
            {
                "app_id": app_id,
                "url": "{}{}/".format(APP_URL, app_id),
                "title": title,
            }
        )
    return rows, html

def discover_page(start:int , count:int =COUNT , filters :Optional[Dict[str, Any]] = None,fixture: Optional[str] = None) -> List[Dict[str, Any]]:
    rows, _ = _search_page(start, count, filters, fixture=fixture)
    return rows
def _genre_filters(genre:Dict[str,Any]):
    filters =dict(DEFAULT_SEARCH_PARAMS)
    if genre.get("tag") is not None:
        filters["tags"] = genre["tag"]
    if genre.get("term"):
        filters["term"]=genre["term"]
    if genre.get("extra"):
        filters.update(genre["extra"])
    return filters
def get_total_results(html:Optional[str])->int:
    if not html:
        return 0
    match = RE_TOTAL_RESULTS.search(html)
    if not match:
        return 0
    raw = match.group("paged")or match.group("count")or "0"
    try:
        return int(raw.replace(",", ""))
    except ValueError:
        return 0
def has_no_more_results(html: Optional[str]) -> bool:
    if not html:
        return True
    return bool(RE_NO_MORE_RESULTS.search(html))

def discover_games(max_games:int = MAX_GAMES,queries:Optional[Sequence[Dict[str,Any]]]=None,per_genre:int=PER_GENRE,count:int=COUNT)->List[Dict[str,Any]]:
    queries = list(GENRES if queries is None else queries)
    if per_genre is None:
        per_genre = max(1, -(-max_games // max(1, len(queries))))
    found:Dict[str,Any] = {}
    order:List[str]=[]

    for query in queries:
        genre_name = query.get("name","unknown")
        filters =_genre_filters(query)
        seen_for_genre = 0
        start = 0

        while seen_for_genre< per_genre and len(found) < max_games:
            rows,html = _search_page(start,count=count,filters=filters)
            if not rows:
                LOGGER.info("GENRE %s | no more rows at start=%d | stopping",
                            genre_name, start)
                break
            for r in rows:
                app_id = r["app_id"]
                if app_id in found:
                    tagged = found[app_id].setdefault("found_in_genres", [])
                    if genre_name not in tagged:
                        tagged.append(genre_name)
                else:
                    if len(found)>= max_games:
                        break
                    r = dict(r)
                    r["found_in_genres"]=[genre_name]
                    found[app_id] = r
                    order.append(app_id)
                seen_for_genre += 1
            total = get_total_results(html)
            start += count
            if total and start>=total:
                LOGGER.info("GENRE %s | reached the end (%d results) at start=%d",
                            genre_name, total, start)
                break
            if has_no_more_results(html):
                LOGGER.info("GENRE %s | the page says there are no more results "
                            "at start=%d | stopping", genre_name, start)
                break
        LOGGER.info("GENRE %s | kept %d rows | unique games so far: %d",
                        genre_name, seen_for_genre, len(found))
    return [found[app_id] for app_id in order]





_RE_APP_NAME = re.compile(
    r'<div id="appHubAppName"[^>]*>(?P<name>.*?)</div>', re.S | re.I
)
# The developer row has an id ("developers_list") but the publisher row has
# none, so both are read by their LABEL ("Developer:" / "Publisher:") inside
# a <div class="dev_row">.
_RE_DEV_ROW_SPLIT = re.compile(r'<div class="dev_row">', re.I)
_RE_ROW_LABEL = re.compile(
    r'<div class="subtitle column">\s*(?P<label>[^<]*?)\s*:\s*</div>', re.S | re.I
)
_RE_ROW_SUMMARY = re.compile(
    r'<div class="summary column"[^>]*>(?P<body>.*?)</div>', re.S | re.I
)
_RE_LINKS = re.compile(r"<a\b[^>]*>(?P<text>.*?)</a>", re.S | re.I)
_RE_DATE = re.compile(r'<div class="date">(?P<date>.*?)</div>', re.S | re.I)
_RE_PRICE = re.compile(
    r'class="discount_final_price[^"]*">(?P<price>.*?)</div>', re.S | re.I
)
_RE_ORIGINAL_PRICE = re.compile(
    r'class="discount_original_price[^"]*">(?P<price>.*?)</div>', re.S | re.I
)
_RE_DISCOUNT_PCT = re.compile(
    r'class="discount_pct"[^>]*>(?P<pct>[^<]*?)<', re.S | re.I
)
_RE_BUY_PRICE = re.compile(
    r'game_purchase_price[^>]*>(?P<price>.*?)</div>', re.S | re.I
)
_RE_REVIEW_SUMMARY = re.compile(
    r'<span class="game_review_summary[^"]*">(?P<summary>.*?)</span>', re.S | re.I
)
_RE_REVIEW_PCT = re.compile(
    r"(?P<pct>\d+)% of the (?P<count>[\d,]+) user reviews", re.I
)
_RE_DESC = re.compile(
    r'<div id="game_area_description"[^>]*>(?P<body>.*?)</div>\s*</div>', re.S | re.I
)
_RE_CATEGORY = re.compile(
    r'class="game_area_details_specs_ctn"[^>]*>.*?<div class="label">'
    r"(?P<label>.*?)</div>",
    re.S | re.I,
    )
# <b>Genre:</b> <span ...><a href=".../genre/Action/...">Action</a>, <a ...>Free to Play</a>
# The page shows the genres twice: once as chips at the top (with the label
# "Free To Play Games") and once in the details block (the canonical
# "Free to Play").  We read the details block first and only fall back to
# the chips, so a genre is not listed twice under two names.
_RE_GENRE_BLOCK = re.compile(r"<b>Genre:</b>(?P<body>.{0,800}?)</span>", re.S | re.I)
_RE_GENRE_LINK = re.compile(
    r'href="https?://store\.steampowered\.com/genre/'
    r'(?P<genre>[^/"?]+)/[^"]*"[^>]*>(?P<name>.*?)</a>',
    re.S | re.I,
    )
# Some pages only carry the price inside a JSON blob, where the markup is
# escaped (\" instead of "), so the live-HTML pattern does not match.
_RE_PRICE_ESCAPED = re.compile(
    r'discount_final_price\\">(?P<price>[^<\\]+)', re.I
)
_RE_PRICE_CENTS = re.compile(r'data-price-final="(?P<cents>\d+)"')

def _clean(text:Optional[str])->str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>"," ",text)
    return re.sub(r"\s+"," ",html_lib.unescape(text)).strip()
def _normalize_game(game: Dict[str, Any]) -> Dict[str, Any]:
    normalized = {}

    for field in RAW_FIELDS:
        value = game.get(field)

        if isinstance(value, str):
            value = _clean(value)
            value = value if value else None

        normalized[field] = value

    return normalized
def _validate_game(game: Dict[str, Any]) -> bool:
    return bool(
        game.get("app_id")
        and game.get("name")
        and game.get("url")
    )

def _dev_and_publishers(html:str)->Dict[str,str]:
    found:Dict[str,List[str]] = {"developer":[], "publisher":[]}
    for chunk in _RE_DEV_ROW_SPLIT.split(html)[1:]:
        label = _RE_ROW_LABEL.search(chunk)
        summary =_RE_REVIEW_SUMMARY.search(chunk)
        if not (label and summary):
            continue
        key = label.group("label").strip().lower()
        if key not in found:
            continue
        names = [_clean(m.group("text")) for m in _RE_LINKS.finditer(summary.group("body"))]
        for name in names:
            if name and name not in found[key]:
                found[key].append(name)
    return {key: "; ".join(names) for key, names in found.items()}

def fallback_extract_app_page(html:str,app_id:str = "")->Dict[str,Any]:
    row:Dict[str,Any] = {field:None for field in RAW_FIELDS}
    row["app_id"] = app_id or None
    row["url"] = "{}{}/".format(APP_URL, app_id) if app_id else None
    row["age_gate"] = "no"
    row["fetch_status"] = "ok"

    name = _RE_APP_NAME.search(html)
    if name:
        row["title"] = _clean(name.group("name"))
    people = _dev_and_publishers(html)
    if people.get("developer"):
        row["developer"] = people["developer"]
    if people.get("publisher"):
        row["publisher"] = people["publisher"]
    date = _RE_DATE.search(html)
    if date:
        row["release_date"] = _clean(date.group("date"))

    price = _RE_PRICE.search(html)
    if price:
        row["price_final"] = _clean(price.group("price"))
    original = _RE_ORIGINAL_PRICE.search(html)
    if original:
        row["price_original"] = _clean(original.group("price"))
    discount = _RE_DISCOUNT_PCT.search(html)
    if discount:
        row["discount_pct"] = _clean(discount.group("pct"))
    if not row.get("price_final"):
        # free-to-play and "buy for X" games show the price elsewhere
        buy = _RE_BUY_PRICE.search(html)
        if buy:
            row["price_final"] = _clean(buy.group("price"))
    if not row.get("price_final"):
        # last resort: the price escaped inside a JSON blob
        escaped = _RE_PRICE_ESCAPED.search(html)
        if escaped:
            row["price_final"] = _clean(escaped.group("price"))

    genres: List[str] = []
    seen_genres = set()
    block = _RE_GENRE_BLOCK.search(html)
    sources = [block.group("body")] if block else []
    sources.append(html)
    for source in sources:
        for match in _RE_GENRE_LINK.finditer(source):
            name = _clean(match.group("name"))
            if not name:
                continue
            key = name.lower()
            if key in seen_genres:
                continue
            seen_genres.add(key)
            genres.append(name)
        if genres:
            break
    if genres:
        row["genres"] = "; ".join(genres)

    cents = _RE_PRICE_CENTS.search(html)
    if cents:
        row["price_final_cents"] = int(cents.group("cents"))

    summary = _RE_REVIEW_SUMMARY.search(html)
    if summary:
        row["review_summary"] = _clean(summary.group("summary"))

    pct = _RE_REVIEW_PCT.search(html)
    if pct:
        row["review_pct_positive"] = int(pct.group("pct"))
        row["review_count"] = int(pct.group("count").replace(",", ""))

    categories = [_clean(m.group("label")) for m in _RE_CATEGORY.finditer(html)]
    categories = [c for c in categories if c]
    if categories:
        row["categories"] = "; ".join(categories)

    desc = _RE_DESC.search(html)
    if desc:
        row["description_short"] = _clean(desc.group("body"))[:1000]

    if row.get("price_final") == "Free To Play" or row.get("price_final") == "Free":
        row["is_free"] = "yes"
    else:
        row["is_free"] = "no"

    return row

def load_extractor():
    if str(DEV_DIR) not in sys.path:
        sys.path.insert(0,str(DEV_DIR))
    for module_name in ("b_parse", "b_extract", "b_parser", "parse_b"):
        try:
            module = __import__(module_name)
        except Exception:
            continue
        candidate = getattr(module, "extract_app_page", None)
        if callable(candidate):
            LOGGER.info("Using extractor from %s.extract_app_page", module_name)
            return candidate, "{}:extract_app_page".format(module_name)
    LOGGER.info("parser not found -- using the built-in fallback extractor")
    return fallback_extract_app_page, "fallback_extract_app_page"


if __name__ == "__main__":
    setup_logging()

    games = discover_page(0, 50, fixture="search_action.html")

    print("Games found:", len(games))
    for g in games[:3]:
        print(g)

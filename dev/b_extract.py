"""this module is for regex extraction of games data from steam store pages.
it has patterns for each field and a main entry point that takes one app page and returns a dict with all the fields.
"""


import re
import glob
import sys
#from a_fetch import RAW_FIELDS
from pathlib import Path


FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures"

#regex flags , S for dotall(match newline ), I for ignorecase(well steam now uses lowercase for all html tags but just for safety)
F = re.S | re.I

RAW_FIELDS = [
    "app_id", "title", "url", "developer", "publisher", "release_date",
    "price_final", "price_original", "discount_pct", "is_free",
    "review_summary", "review_count", "review_pct_positive", "metacritic_score",
    "genres", "categories", "tags", "platforms", "description_short", "dlc_count",
    "age_gate", "fetch_status",
]

#the compiled patterns ,one re.compile per field


#html for title is in a div with id="appHubAppName" , so we take the group between the opening and closing div tags
#note : we can aso use [^<]+ instead of non greedy (it fails louder)
RE_TITLE=re.compile(r'<div id="appHubAppName"[^>]*>(?P<v>.*?)</div>',F)

#release date even for upcoming games(coming soon date) is in a div with class="date" , so we take the group between the opening and closing div tags
#date format is ex: apr 18, 2011
RE_RELEASE_DATE=re.compile(r'<div class="date">(?P<v>.*?)</div>')

#i have seen some games with multiple developers and publishers , so we take the group between the opening and closing div tags with id="developers_list" and id="publishers_list" respectively
#links to developer and publisher pages are in the form of <a href=link>DEVELOPER_NAME</a> and <a "link">PUBLISHER_NAME</a>
RE_DEV_BLOCK = re.compile(r'Developer:</div>\s*<div class="summary column"[^>]*>(?P<v>.*?)</div>', F)

RE_PUB_BLOCK = re.compile(r'Publisher:</div>\s*<div class="summary column"[^>]*>(?P<v>.*?)</div>', F)

#etract the text between the opening and closing a tags , we will use this to extract the developer and publisher names from the blocks above
#[^<]+ takes only the text up to the next <, so a link name never carries tags into the CSV
RE_LINK_TEXT=re.compile(r'<a\b[^>]*>(?P<v>[^<]+)</a>', F)

#capture the genre block and then extract the genre names from the links inside it
RE_GENRES = re.compile(r'<b>Genre:</b>(?P<v>.*?)<br>', F)

#exctcrat from meta , easier and more reliable than the description in the body of the page
#takes the content attribute of the meta tag with name="Description" , stops at the first double quote after the content attribute
RE_DESC= re.compile(r'<meta name="Description" content="(?P<v>[^"]*)"', F)


#extract one tag at a time from </a> <a href="link" class= "app_tag" > user tag </a> (later findall)
RE_TAG=re.compile(r'<a\b[^>]*class="app_tag"[^>]*>(?P<v>.*?)</a>',F )

# Isolate the base game's buy box so we don't accidentally extract prices from DLCs or bundles
RE_BUYBOX = re.compile(r'<div class="game_purchase_action_bg">(?P<v>.*?)<div[^>]*class="btn_addtocart', F)
# Extract the discount percentage (ex -50%)
RE_DISC_PCT = re.compile(r'<div class="discount_pct"[^>]*>(?P<v>-?\d+%)</div>', F)
# Extract the original price before the discount (ex $4.99)
RE_DISC_ORIG = re.compile(r'<div class="discount_original_price">(?P<v>[^<]+)</div>', F)
# Extract the final discounted price (ex $2.49)
RE_DISC_FINAL = re.compile(r'<div class="discount_final_price">(?P<v>[^<]+)</div>', F)
# Extract the normal game price or "Free To Play", ignoring spaces and HTML attributes
RE_PRICE = re.compile(r'<div class="game_purchase_price price"[^>]*>\s*(?P<v>[^<]*?)\s*</div>', F)

#we have label , percentage and count of reviews in the reviews section of the page , we take them from the div with class="subtitle column all" and then the span with class="game_review_summary" and the literal brackets around the percentage and count
RE_REVIEW=re.compile(r'<div class="subtitle column all">\s*(?:All|English) Reviews:</div>'
                     #<span class="game_review_summary positive" itemprop="description">Very Positive</span>
                     r'(?:(?!</a>).)*?<span class="game_review_summary[^"]*"[^>]*>(?P<label>[^<]+)</span>'
                     r'(?:(?!</a>).)*?\((?P<pct>\d+)% of (?P<count>[\d,]+)\)'  #literal brackets btw
                     ,F
                     )

#here i used the tempered dot : any chars, but never past </a> cuz Each review row ends with </a>, so the match cannot jump into the next row
#if we use .*? : on a no-review game it could grab a number from an unrelated place.


#match the metascore in the div with id="game_area_metascore" and class="score ..." , take the number inside the div
RE_META = re.compile(r'id="game_area_metascore">\s*<div class="score \w+">\s*(?P<v>\d+)', F)


# Platforms: first purchase platform box, then its icon spans.
#ex: <div class="game_area_purchase_platform"><span class="platform_img win"></span></div>

RE_PLAT_BOX = re.compile(r'<div class="game_area_purchase_platform">(?P<v>.*?)</div>', F)
RE_PLAT = re.compile(r'platform_img (?P<v>win|mac|linux)', F)

#ex: <div class="label">Single-player</div></a>
#we capture the text inside the div with class="label"
RE_CATEGORY = re.compile(r'<div class="label">(?P<v>[^<]+)</div></a>', F)

# DLC count: "Browse all <em>(3)".
RE_DLC = re.compile(r'Content For This Game.*?Browse all\s*<em>\((?P<v>\d+)\)', F)

# Age gate flag in page JSON (quotes are HTML-escaped). null / 0 do not match.
RE_AGE = re.compile(r'use_age_gate&quot;:\s*(?:true|[1-9])', F)






"""helper methods for extracting data from the html using the regexes above"""

#clean raw data (only whitespace and new line)

def clean(text):
    if text is None:
        return None
    #sub all whitespace sequences with a single space, then strip leading spaces
    text = re.sub(r"\s+", " ", text).strip()
    return text or None

#extract first match of a pattern from html using search regex function , return the cleaned group text or None if not found
def first(pattern, html, group="v"):
    m = pattern.search(html)
    return clean(m.group(group)) if m else None #clean the group text if match found, else return None



#useful for developers, publishers and genres because they can have multiple links
#
def link_texts(pattern, html):
    """Block pattern, then every link text inside it, joined by ';'."""
    m = pattern.search(html)
    if not m:
        return None
    names = []
    for x in RE_LINK_TEXT.findall(m.group("v")):  #finds every link's text inside that block and clean it
        name = clean(x)
        if name:
            names.append(name) #add ach valid name to the list
    return ";".join(names) or None #combines the names into one string separated by ;




#getters for each field , return None if not found

def get_title(html):
    return first(RE_TITLE, html)


def get_release_date(html):
    return first(RE_RELEASE_DATE, html)


def get_developer(html):
    return link_texts(RE_DEV_BLOCK, html)


def get_publisher(html):
    return link_texts(RE_PUB_BLOCK, html)


def get_genres(html):
    return link_texts(RE_GENRES, html)


def get_description(html):
    return first(RE_DESC, html)

#
def get_tags(html, limit=5):
    #First limit user tags joined by ;
    tags = []
    for t in RE_TAG.findall(html):
        t = clean(t)
        if t:
            tags.append(t)
    return ";".join(tags[:limit]) or None #keeps only the first five by default


def get_metascore(html):
    return first(RE_META, html)

def get_dlc_count(html):
    return first(RE_DLC, html)


def get_age_gate(html):
    return "yes" if RE_AGE.search(html) else "no"

def get_price(html):
    #Returns price_final, price_original, discount_pct, is_free (raw strings)
    out = {"price_final": None, "price_original": None, "discount_pct": None, "is_free": None}
    box = RE_BUYBOX.search(html)
    if not box:
        return out
    b = box.group("v")
    if first(RE_DISC_FINAL, b):  # discounted
        out["price_final"] = first(RE_DISC_FINAL, b)
        out["price_original"] = first(RE_DISC_ORIG, b)
        out["discount_pct"] = first(RE_DISC_PCT, b)
        out["is_free"] = "no"
    elif first(RE_PRICE, b):
        out["price_final"] = first(RE_PRICE, b)
        out["is_free"] = "yes" if "free" in out["price_final"].lower() else "no"
    return out


def get_reviews(html):
    #Returns review_summary, review_count, review_pct_positive (raw strings)
    m = RE_REVIEW.search(html)  # NOTE: was RE_REVIEWS (name did not exist)
    if not m:
        return {"review_summary": None, "review_count": None, "review_pct_positive": None}
    return {"review_summary": clean(m.group("label")),
            "review_count": m.group("count"),
            "review_pct_positive": m.group("pct")}



def get_platforms(html):
    m = RE_PLAT_BOX.search(html)
    if not m:
        return None
    found = []
    for p in RE_PLAT.findall(m.group("v")):
        if p.lower() not in found:
            found.append(p.lower())
    return ";".join(found) or None


def get_categories(html):
    found = []
    for c in RE_CATEGORY.findall(html):
        c = clean(c)
        if c and c not in found:
            found.append(c)
    return ";".join(found) or None






"""" main entry"""

def extract_app_page(html, app_id=None):
    #One app page -> dict with exactly RAW_FIELDS keys. Missing = None. Never raises. app_id is optional: if given it is copied into the record (A may pass it)
    rec = {}
    for k in RAW_FIELDS:
        rec[k] = None
    if app_id:
        rec["app_id"] = str(app_id)
        rec["url"] = "https://store.steampowered.com/app/" + str(app_id) + "/"
    if not html:
        rec["fetch_status"] = "empty"
        return rec
    getters = [
        lambda: {"title": get_title(html)},
        lambda: {"release_date": get_release_date(html)},
        lambda: {"developer": get_developer(html)},
        lambda: {"publisher": get_publisher(html)},
        lambda: {"genres": get_genres(html)},
        lambda: {"description_short": get_description(html)},
        lambda: get_price(html),
        lambda: get_reviews(html),
        lambda: {"metacritic_score": get_metascore(html)},
        lambda: {"platforms": get_platforms(html)},
        lambda: {"categories": get_categories(html)},
        lambda: {"tags": get_tags(html)},
        lambda: {"dlc_count": get_dlc_count(html)},
        lambda: {"age_gate": get_age_gate(html)},
    ]
    for g in getters:
        try:
            rec.update(g())
        except Exception: #one bad regex or a change in the page format should not crash the whole extraction, just skip that field
            pass
    rec["fetch_status"] = "ok"
    return rec


def coverage(records):
    #records then prints and returns {field: % non-null}
    fields = []
    for f in RAW_FIELDS:
        if f not in ("app_id", "url", "fetch_status"):
            fields.append(f)
    n = len(records) or 1
    result = {}
    for f in fields:
        filled = 0
        for r in records:
            if r.get(f):
                filled += 1
        result[f] = 100.0 * filled / n
        print(f"{f:22} {result[f]:5.1f}%")
    return result


if __name__ == "__main__":
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else FIXTURE_DIR
    records = []
    for path in sorted(folder.glob("*.html")):
        if path.name.startswith("search"):
            continue
        rec = extract_app_page(path.read_text(encoding="utf-8", errors="replace"))
        if rec["title"] is None:  # not an app page (search page, test page)
            print(f"{path.name:24} skipped (no title)")
            continue
        records.append(rec)
        print(f"{path.name:24} {rec['title']!s:22} {rec['developer']!s:16} "
              f"{rec['release_date']!s:14} {rec['price_final']!s:12} {rec['review_pct_positive']!s:>4}")
    print()
    coverage(records)
 
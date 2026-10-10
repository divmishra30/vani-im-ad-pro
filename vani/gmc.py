"""Google Merchant Centre (GMC) data for a seller, ported from ads-next (app/api/gmc-feed, lib/gmcFeed.ts).

Two IndiaMART services, both needing the user's AK token (the AK_Key cookie ads-next sets on Google
sign-in, valid for about a day):
  - users.imutils.com  product listing, paginated  -> every product with price, images, specs, MCAT
  - seller.imutils.com Merchant Centre ad listing  -> which products are Live / Pending in GMC
Joined on Display ID like ads-next: Live, Pending, or Unavailable (never pushed). Snapshots are cached in
data/gmc/<glid>.json, so calls keep working after the AK token expires.

Read-only: nothing here pushes to or deletes from Merchant Centre.
"""

import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
import re
import threading

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "gmc"
PRODUCTS_URL = "http://users.imutils.com/wservce/products/userproductslisting/"
MERCHANT_CENTRE_URL = "http://seller.imutils.com/wservce/products/selleradsglusrproductslisting/"
MAX_PAGES = 40  # page 1 has 100 products, later pages 50: ~2,000 products
TIMEOUT = 30


def _env(name):
    return os.environ.get(name, "").strip()


def ak_status():
    """(ok, message) for the AK token in .env, checking its expiry like ads-next does."""
    token = _env("IM_AK_TOKEN")
    if not token:
        return False, "IM_AK_TOKEN is not set"
    try:
        part = token.split(".")[1]
        exp = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))).get("exp")
    except (IndexError, ValueError):
        return False, "IM_AK_TOKEN is not a valid JWT"
    if exp and time.time() > exp:
        return False, f"IM_AK_TOKEN expired at {datetime.fromtimestamp(exp):%d %b %H:%M}"
    return True, f"valid until {datetime.fromtimestamp(exp):%d %b %H:%M}" if exp else "valid"


SECRET_PARAMS = ("AK", "token")
_local = threading.local()  # per-thread API log for the fetch in progress, so concurrent fetches don't mix


def calls():
    """API requests made by the current (or last) fetch on this thread."""
    return getattr(_local, "calls", [])


def log(msg):
    print(f"[gmc] {msg}", flush=True)


def _get(url, params):
    shown = urllib.parse.urlencode({k: ("***" if k in SECRET_PARAMS else v) for k, v in params.items()})
    entry = {"url": f"{url}?{shown}", "page": params.get("pg_type")}
    t = time.time()
    try:
        req = urllib.request.Request(f"{url}?{urllib.parse.urlencode(params)}", headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read()
            entry.update(status=resp.status, bytes=len(body))
        data = json.loads(body)
        entry["records"] = len(data) if isinstance(data, list) else "object"
        return data
    except urllib.error.HTTPError as e:
        entry["status"] = e.code
        raise
    except Exception as e:
        entry["error"] = str(e)[:120]
        raise
    finally:
        entry["ms"] = round((time.time() - t) * 1000)
        calls().append(entry)
        log(f"GET {entry['url']} -> {entry.get('status', 'ERR')} {entry.get('records', '')} records "
            f"{entry.get('bytes', 0) // 1024}KB {entry['ms']}ms" + (f" ({entry['error']})" if entry.get("error") else ""))


def _page(glid, page):
    data = _get(PRODUCTS_URL, {
        "AK": _env("IM_AK_TOKEN"), "token": _env("IM_PRODUCTS_TOKEN"), "APP_SCREEN_NAME": "My-Product-Listing",
        "gluserid": glid, "ordering": "3", "product_filter": "ALL", "pg_type": str(page),
        "modid": "andweb", "extra_detail": "multi_img,isq", "mod_id": "ANDWEB"})
    if not isinstance(data, list):  # a non-array body means the AK token was rejected
        raise RuntimeError("product listing rejected the request; the AK token may have expired")
    return data


def _statuses(glid):
    """Display ID -> Live/Pending from the Merchant Centre ad listing (a Live record wins)."""
    data = _get(MERCHANT_CENTRE_URL, {"glid": glid, "token": _env("IM_PRODUCTS_TOKEN"), "AK": _env("IM_AK_TOKEN")})
    items = (data.get("Response") or {}).get("Data") if isinstance(data, dict) else None
    if items is None and isinstance(data, dict):
        items = data.get("Data")
    out = {}
    for p in items or []:
        did = str(p.get("DISPLAY_ID") or "").strip()
        if did and (str(p.get("AD_STATUS")) == "1" or did not in out):
            out[did] = "Live" if str(p.get("AD_STATUS")) == "1" else "Pending"
    return out


def _text(html):
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]*>", " ", html or ""))).strip()


def _row(p):
    price = str(p.get("PC_ITEM_FOB_PRICE") or "").replace(",", "").strip()
    try:
        price = f"{float(price):.0f}" if float(price) > 0 else ""
    except ValueError:
        price = ""
    specs = [f"{(i.get('FK_IM_SPEC_MASTER_DESC') or i.get('IM_SPEC_MASTER_DESC') or '').strip()}: "
             f"{(i.get('SUPPLIER_RESPONSE_DETAIL') or i.get('ISQ_RESPONSE') or '').strip()}"
             for i in p.get("ISQ_DETAIL") or [] if i and (i.get("SUPPLIER_RESPONSE_DETAIL") or i.get("ISQ_RESPONSE"))]
    product_type = next((t.strip() for t in str(p.get("MCAT_NAME_LIST") or "").split(",") if t.strip()), "")
    return {
        "id": str(p.get("PC_ITEM_DISPLAY_ID") or "").strip(),
        "title": str(p.get("ITEM_NAME") or "").strip(),
        "price": price,
        "in_stock": str(p.get("PC_ITEM_STATUS_APPROVAL") or "").strip() != "9",
        "image": str(p.get("IMAGE_PATH4") or "").strip(),
        "extra_images": sum(1 for i in p.get("MULTI_ITEM_IMG_DETAIL") or [] if i and i.get("pc_item_image_original")),
        "description": _text(p.get("SMALL_DESCRIPTION"))[:300],
        "specs": len(specs),
        "mcat_id": str(p.get("MCATID") or "").strip(),
        "product_type": product_type,
        "link": str(p.get("PDP_URL") or "").strip(),
    }


def fetch(glid):
    """Fetch a fresh snapshot for one seller and cache it. Raises with a readable message on failure."""
    ok, why = ak_status()
    if not ok:
        raise RuntimeError(why)
    if not _env("IM_PRODUCTS_TOKEN"):
        raise RuntimeError("IM_PRODUCTS_TOKEN is not set")
    _local.calls = []
    started = time.time()
    log(f"fetching seller {glid}")
    try:
        records, page = _page(glid, 1), 1
        while records and page < MAX_PAGES:  # only an empty page marks the end (page sizes vary)
            more = _page(glid, page + 1)
            page += 1
            if not more:
                break
            records += more
        try:
            statuses, status_error = _statuses(glid), ""
        except (urllib.error.URLError, ValueError, TimeoutError) as e:
            statuses, status_error = {}, f"Merchant Centre status unavailable: {e}"
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"IndiaMART product listing returned HTTP {e.code}") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise RuntimeError(f"could not reach the IndiaMART product service ({e}); are you on the office network/VPN?") from e

    rows, seen = [], set()
    for r in map(_row, records):
        if r["id"] in seen:
            continue
        seen.add(r["id"])
        r["status"] = "Unknown" if status_error or not r["id"] else statuses.get(r["id"], "Unavailable")
        rows.append(r)
    snap = {"glid": glid, "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "product_count": len(rows), "status_error": status_error, "rows": rows,
            "api_log": list(calls()), "fetch_ms": round((time.time() - started) * 1000)}
    log(f"seller {glid}: {len(rows)} products ({sum(r['status'] == 'Live' for r in rows)} live) "
        f"in {len(calls())} requests, {snap['fetch_ms']}ms")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / f"{glid}.json").write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
    return snap


def load(glid):
    """The cached snapshot, or None. Never touches the network."""
    path = CACHE_DIR / f"{glid}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def age_hours(snap):
    return (datetime.now(timezone.utc) - datetime.fromisoformat(snap["fetched_at"])).total_seconds() / 3600


def quality(r):
    """Feed-quality score (0-5): what Google needs to show a product often."""
    return sum([bool(r["price"]), bool(r["image"]), len(r["description"]) >= 50, r["specs"] >= 3, r["extra_images"] >= 1])


def issues(r):
    return [label for label, bad in (("no price", not r["price"]), ("no photo", not r["image"]),
                                     ("short description", len(r["description"]) < 50), ("few specs", r["specs"] < 3),
                                     ("out of stock", not r["in_stock"])) if bad]


def for_category(snap, mcat_id, category):
    """Products in one ad category: matched on MCAT id, else on the product type name."""
    name = (category or "").strip().lower()
    return [r for r in snap["rows"] if (mcat_id and r["mcat_id"] == str(mcat_id)) or (name and r["product_type"].lower() == name)]


PRODUCT_ADS_FILE = CACHE_DIR.parent / "Product data.csv"  # product_id (= GMC display id), mcat, total_impressions
MIN_PRODUCTS = 10  # below this the category has too few products to show often
TOP_N = 3
_impressions, _mcat_impressions = {}, {}


def _load_sheet():
    if _impressions or not PRODUCT_ADS_FILE.exists():
        return
    import csv
    with open(PRODUCT_ADS_FILE, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            try:
                n = int(float(r["total_impressions"] or 0))
            except ValueError:
                continue
            _impressions[r["product_id"].strip()] = n
            mcat = r["mcat"].strip().lower()
            _mcat_impressions[mcat] = _mcat_impressions.get(mcat, 0) + n
    _impressions.setdefault("", 0)  # mark as loaded even if the sheet is empty


def impressions(product_id):
    """Google Ads impressions for one product from the product ads sheet (0 if it has none)."""
    _load_sheet()
    return _impressions.get(str(product_id), 0)


def category_impressions(name):
    """Google Ads impressions for every product in a category (the sheet's mcat column): market demand."""
    _load_sheet()
    return _mcat_impressions.get((name or "").strip().lower(), 0)


def other_campaigns(snap, advertised_ids, advertised_names, limit=3, min_products=2):
    """Upsell: categories where the seller lists products but runs no ad campaign, ranked by Google Ads demand.

    Each: name, mcat_id, products (count), market_impressions (whole category in the product ads sheet),
    top (the seller's best 3 products there, by impressions then listing quality)."""
    advertised_ids = {str(i) for i in advertised_ids if i}
    advertised_names = {n.strip().lower() for n in advertised_names if n}
    groups = {}
    for r in snap["rows"]:
        if not r["product_type"] or r["mcat_id"] in advertised_ids or r["product_type"].lower() in advertised_names:
            continue
        groups.setdefault(r["mcat_id"] or r["product_type"].lower(), []).append(r)
    out = []
    for key, rows in groups.items():
        if len(rows) < min_products:
            continue
        names = {}
        for r in rows:
            names[r["product_type"]] = names.get(r["product_type"], 0) + 1
        name = max(names, key=names.get)
        for r in rows:
            r["impressions"] = impressions(r["id"])
        top = sorted(rows, key=lambda r: (-r["impressions"], -quality(r)))[:TOP_N]
        out.append({"name": name, "mcat_id": rows[0]["mcat_id"], "products": len(rows),
                    "market_impressions": category_impressions(name), "top": [r["title"] for r in top]})
    # Demand weighted by depth: a campaign needs products to rotate, so 2 products count for 20% of 10+.
    out.sort(key=lambda c: (-c["market_impressions"] * min(c["products"], MIN_PRODUCTS) / MIN_PRODUCTS, -c["products"]))
    return out[:limit]


def campaign(snap, mcat_id, category):
    """What the improve call needs about one ad category, from real GMC data plus the product ads sheet.

    Pitch rules (products in this category per the GMC listing):
      - fewer than 10: add every other product the seller has here that isn't in the campaign yet
      - 10 or more:    add the top 3 of those by Google Ads impressions (product ads sheet)
      - none to add:   ask the seller to list more products in this category
    """
    rows = for_category(snap, mcat_id, category)
    for r in rows:
        r["impressions"] = impressions(r["id"])
    live = [r for r in rows if r["status"] == "Live"]
    pending = [r for r in rows if r["status"] == "Pending"]
    addable = [r for r in rows if r["status"] == "Unavailable" and r["in_stock"] and r["title"]]
    if len(rows) < MIN_PRODUCTS:
        mode, pitch = "add_other", sorted(addable, key=lambda r: (-r["impressions"], -quality(r)))
    else:
        mode, pitch = "top_performers", sorted(addable, key=lambda r: (-r["impressions"], -quality(r)))[:TOP_N]
    if not pitch:
        mode = "list_more"
    counts = {}
    for r in live:
        for i in issues(r):
            counts[i] = counts.get(i, 0) + 1
    return {"in_category": len(rows), "live": len(live), "pending": len(pending), "candidates": pitch, "mode": mode,
            "addable": len(addable), "issue_counts": counts, "rows": rows,
            "top_live": sorted((r for r in live if r["impressions"]), key=lambda r: -r["impressions"])[:TOP_N]}


def issues_line(c):
    """One spoken-friendly line about fixable feed problems on the live products."""
    if not c["live"]:
        return ""
    parts = [f"{n} of {c['live']} live products have {label}" for label, n in sorted(c["issue_counts"].items(), key=lambda x: -x[1])]
    return "; ".join(parts[:3])

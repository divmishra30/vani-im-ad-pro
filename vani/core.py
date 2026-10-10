"""VANI core: lead reports -> call triggers -> per-seller context (seller.md, opening line, variables)."""

import csv
import hashlib
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from . import gmc

ROOT = Path(__file__).resolve().parent.parent
DATA, OUT = ROOT / "data", ROOT / "sarvam"

MIN_ORGANIC_LEADS = 200  # upsell: candidate MCAT needs >200 buyer enquiries/month
TARGET_PRODUCTS = 10  # improve: campaigns below this get product suggestions
TIER_PRICE = {"Standard": 12000, "Premium": 18000, "Platinum": 30000}  # MOCK plan prices
DEMO_SELLERS = ["154979145", "118932009", "132281146"]  # renew, upsell, improve
PRIORITY = {"renew": 0, "upsell": 1, "improve": 2}
LABEL = {"renew": "RENEWAL DUE", "upsell": "UPSELL", "improve": "IMPROVE"}


def num(s):
    try:
        return float((s or "").replace("%", ""))
    except ValueError:
        return 0.0


def read_csv(name):
    path = DATA / name
    if not path.exists():
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        return [{k.strip(): (v or "").strip() for k, v in row.items()} for row in csv.DictReader(f)]


def load_work_orders():
    windows = {r["Work Order"]: r for r in read_csv("lead-report.csv")}
    wos = []
    for v in read_csv("lead-report-pmcat.csv"):
        w = windows.get(v["Work Order"], {})
        wos.append({
            "seller_id": v["Seller ID"],
            "seller_name": v["Seller Name"],
            "work_order": v["Work Order"],
            "mcat_id": v["Remapped MCAT ID"],
            "category": v["Remapped MCAT Name"] or "your category",
            "pmcat_id": v["PMCAT ID"],
            "pmcat_name": v["PMCAT Name"],
            "tier": v["Tier"],
            "manager": v["Manager"],
            "lead_count": int(num(v["Lead Count"])),
            "delivered": int(num(v["Actual Delivery"])),
            "delivery_pct": round(num(v["Delivery %"])),
            "act_bucket": v["Act. Del. Bucket"],
            "live": v["Campaign Live"] == "Yes",
            "avg_bl_month": num(v["Avg BL/Month (12M)"]),
            "renewal_status": v["Renewal Status"],
            "leads_7d": int(num(w.get("7D Leads"))),
            "leads_28d": int(num(w.get("28D Leads"))),
            "delivery_28d_pct": round(num(w.get("28D Delivery%"))),
            "bucket_28d": w.get("28D Delivery% Bucket", ""),
            "buyers_gst": int(num(w.get("Buyer with GST"))),
        })
    return wos


# --- Call triggers, per work order --------------------------------------------------------
#   1. Act. Del. Bucket >80%   -> renew
#   2. Act. Del. Bucket 50-80% -> upsell
#   3. 28D Delivery% <50%      -> improve (only if neither rule above fired)
def reason_for(wo):
    if wo["act_bucket"] == ">80%":
        return "renew"
    if wo["act_bucket"] == "50-80%":
        return "upsell"
    if wo["act_bucket"] and wo["bucket_28d"] == "<50%":
        return "improve"
    return None  # WIP (no delivery data) or healthy in the last 28 days


def pick_primary(hits):
    # One call per seller: most urgent work order first; within renew/upsell the most-used
    # package, within improve the worst 28-day delivery.
    def key(h):
        reason, wo = h
        tie = wo["delivery_28d_pct"] if reason == "improve" else -wo["delivery_pct"]
        return (PRIORITY[reason], tie)
    return sorted(hits, key=key)[0]


# --- Upsell: tier A = same PMCAT, tier B = PMCATs of the seller's other work orders -----------
def pmcat_tree(wos):
    """PMCAT -> {MCAT id: (name, buyer enquiries/month)}.

    MCATs come from data/mcat-pmcat-mapping.csv plus the report. Demand per MCAT is the
    report's Avg BL/Month (12M), or a demand column in the mapping file for MCATs the report
    doesn't have. MCATs without known demand can't pass the >200 rule, so they're skipped.
    """
    demand = {w["mcat_id"]: w["avg_bl_month"] for w in wos if w["mcat_id"]}
    tree = defaultdict(dict)
    for m in read_csv("mcat-pmcat-mapping.csv"):
        leads = demand.get(m["MCAT ID"], num(m.get("Avg BL/Month (12M)") or m.get("Organic Leads/Month")))
        if leads:
            tree[m["PMCAT ID"]][m["MCAT ID"]] = (m["MCAT Name"], leads)
    for w in wos:
        if w["pmcat_id"] and w["mcat_id"]:
            tree[w["pmcat_id"]].setdefault(w["mcat_id"], (w["category"], w["avg_bl_month"]))
    return tree


def upsell_for(wo, seller_wos, tree):
    advertised = {w["mcat_id"] for w in seller_wos}

    def pick(pmcat_ids):
        found = [(name, leads) for p in pmcat_ids for mid, (name, leads) in tree[p].items()
                 if leads > MIN_ORGANIC_LEADS and mid not in advertised]
        return sorted(found, key=lambda x: -x[1])

    tier_a = pick([wo["pmcat_id"]])
    if tier_a:
        return "A", tier_a[0]
    others = {w["pmcat_id"] for w in seller_wos if w["pmcat_id"] and w["pmcat_id"] != wo["pmcat_id"]}
    tier_b = pick(others)
    return ("B", tier_b[0]) if tier_b else ("", ("", 0))


# --- Campaign products: real GMC data when fetched (vani/gmc.py), otherwise MOCK ----------
def gmc_campaign(wo):
    """This ad category's products from the cached GMC snapshot, or None if there is no usable snapshot."""
    snap = gmc.load(wo["seller_id"])
    if not snap:
        return None
    c = gmc.campaign(snap, wo["mcat_id"], wo["category"])
    return c if c["in_category"] else None



def h(s):
    return int(hashlib.md5(s.encode()).hexdigest(), 16)


VARIANTS = ["Heavy Duty", "Standard Model", "Premium Grade", "Compact", "Industrial",
            "Automatic", "Economy", "Stainless Steel", "Export Quality", "Customised"]


def gmc_new_campaigns(seller_wos):
    """Categories the seller lists products in (GMC) but has no ad campaign for, best Google demand first."""
    snap = gmc.load(seller_wos[0]["seller_id"]) if seller_wos else None
    if not snap:
        return []
    return gmc.other_campaigns(snap, [w["mcat_id"] for w in seller_wos], [w["category"] for w in seller_wos])


def spoken_title(title, words=6):
    """A product title short enough to say on a call: no trailing dots or doubled spaces, at most 6 words."""
    parts = title.replace("  ", " ").strip().rstrip(".").split()[:words]
    while len(parts) > 2 and not any(ch.isalpha() for ch in parts[-1]):  # no dangling "8 +" or "3.5"
        parts.pop()
    return " ".join(parts)


def plan_options(tier):
    """Spoken list of the IM Ad Pro plans (MOCK prices), marking the seller's current one."""
    return ", ".join(f"{t} {p:,} rupees" + (" (current)" if t == tier else "") for t, p in TIER_PRICE.items())


def product_count(wo):
    c = gmc_campaign(wo)
    return c["live"] if c else min(TARGET_PRODUCTS, 3 + h(wo["work_order"]) % 12)


def product_suggestions(wo):
    """With GMC data: the seller's own products in this category not yet in Merchant Centre, best feed quality first.
    Without: peer products in the same MCAT, scored 0.5*CTR_norm + 0.5*conversions_norm (MOCK)."""
    c = gmc_campaign(wo)
    if c:
        return [r["title"] for r in c["candidates"]]
    seed = h(wo["mcat_id"] or wo["work_order"])
    items = []
    for i, v in enumerate(VARIANTS):
        ctr, conv = 1 + (seed >> i) % 40 / 10, 2 + (seed >> (i + 3)) % 30
        items.append({"name": f"{v} {wo['category']}", "ctr": ctr, "conv": conv, "own": (seed >> i) % 3 != 0})
    max_ctr, max_conv = max(i["ctr"] for i in items), max(i["conv"] for i in items)
    for i in items:
        i["score"] = 0.5 * i["ctr"] / max_ctr + 0.5 * i["conv"] / max_conv
    return [i["name"] for i in sorted(items, key=lambda i: -i["score"]) if i["own"]]


# --- Per-seller context -------------------------------------------------------------------
def opening_line(name, reason, wo, upsell_cat, last=None):
    who = f"Kya meri baat {name} se ho rahi hai?" if name else "Kya meri baat IndiaMART Ads lene wale seller se ho rahi hai?"
    if last:  # returning seller: pick up from the last conversation instead of starting cold
        d = last["data"]
        when = f"{int(last['at'][8:10])} {MONTHS[int(last['at'][5:7]) - 1]}"
        t = (d.get("callback_time") or "").strip()
        asked = f", aur aapne {t}{'' if t.endswith(' ko') else ' ko'} baat karne ko kaha tha" if t else ""
        return (f"Namaste! Main IndiaMART se VANI bol rahi hoon. {who} {when} ko humne aapke {wo['category']} ads ke baare mein "
                f"baat ki thi{asked}. Usi ke aage baat karni thi, do minute hain?")
    if reason == "renew":
        hook = (f"Aapke {wo['category']} ads ke package ki saari {wo['lead_count']} leads deliver ho chuki hain"
                if wo["delivery_pct"] >= 100 else
                f"Aapke {wo['category']} ads ki {wo['delivery_pct']} percent delivery ho chuki hai")
        hook += ", isliye renewal ke baare mein baat karni thi."
    elif reason == "upsell":
        hook = (f"Aapke {wo['category']} ads achhe chal rahe hain, aur {upsell_cat} mein bhi aapke liye achhi demand dikh rahi hai."
                if upsell_cat else f"Aapke {wo['category']} ads achhe chal rahe hain, usi ke baare mein ek suggestion dena tha.")
    else:
        hook = f"Aapke {wo['category']} ads ki leads pichle 28 din mein kam aayi hain, unhe badhane ke kuch tareeke batane the."
    return f"Namaste! Main IndiaMART se VANI bol rahi hoon. {who} {hook} Do minute baat kar sakte hain?"


MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
TRANSCRIPT_CHARS = 1500  # how much of the last call goes into seller.md (it is also an agent variable)


def last_call(history):
    """The most recent call that has a transcript or summary, or None."""
    return next((e for e in history if e["type"] == "outcome" and (e["data"].get("transcript") or e["data"].get("summary"))), None)


def transcript_excerpt(text, limit=TRANSCRIPT_CHARS):
    """The end of a transcript (where decisions are made), cut on a line boundary."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    tail = text[-limit:]
    return "[...]\n" + tail[tail.find("\n") + 1:]


def seller_md(row, primary, seller_wos, history=()):
    lines = [
        f"# Seller {row['glid']}" + (f" · {row['seller_name']}" if row["seller_name"] else ""),
        f"generated: {datetime.now():%Y-%m-%d %H:%M} · manager: {primary['manager'] or 'n/a'}",
        f"call reason: {LABEL[row['call_reason']]} for {row['category']}",
        "",
        "## Ads (IM Ad Pro)",
    ]
    for w in seller_wos[:6]:
        r = reason_for(w)
        lines.append(
            f"- {w['category']} ({w['pmcat_name'] or 'no parent'}; {w['tier']}, {'live' if w['live'] else 'not live'}): "
            f"delivered {w['delivery_pct']}% ({w['delivered']}/{w['lead_count']} leads), last 28d {w['delivery_28d_pct']}% "
            f"({w['leads_28d']} leads), {product_count(w)} products" + (f" -> {LABEL[r]}" if r else ""))
    lines += [
        f"- Last plan price (mock): INR {row['plan_price']:,} for {row['lead_count']} leads",
        "",
        "## Upsell candidate (>200 buyer enquiries/month)",
        (f"- {row['upsell_category']}: from the seller's GMC listing (see New campaigns below)" if row["upsell_tier"] == "GMC" else
         f"- {row['upsell_category']}: {row['upsell_organic_leads']}/month, tier {row['upsell_tier']}")
        if row["upsell_category"] else "- none qualifies",
        "",
        "## Leads",
        f"- {row['category']}: {primary['leads_7d']} in 7d, {row['leads_28d']} in 28d, {primary['buyers_gst']} buyers with GST",
        "",
        *gmc_lines(primary),
        *new_campaign_lines(row, seller_wos),
        "## History (newest first)",
        *([f"- {line}" for line in map(history_line, history[:6]) if line] or ["- no previous contact"]),
    ]
    open_items = [e["data"]["next_step"] for e in history if e["type"] == "outcome" and e["data"].get("next_step")]
    if open_items:
        lines += ["", "## Open item from last contact", f"- {open_items[0]}"]
    last = last_call(history)
    if last:
        d = last["data"]
        lines += ["", f"## Last conversation ({last['at'][:10]}, {d.get('channel') or 'call'})"]
        if d.get("summary"):
            lines.append(f"Summary: {d['summary']}")
        if d.get("transcript"):
            lines += ["Transcript (end of call):", transcript_excerpt(d["transcript"])]
    return "\n".join(lines)


def gmc_lines(wo):
    """seller.md section from the cached Google Merchant Centre snapshot (empty without one)."""
    snap = gmc.load(wo["seller_id"])
    if not snap:
        return []
    c = gmc_campaign(wo)
    lines = [f"## Google Merchant Centre (fetched {snap['fetched_at'][:10]})",
             f"- All products: {snap['product_count']}, of which {sum(r['status'] == 'Live' for r in snap['rows'])} live in Merchant Centre"]
    if not c:
        lines.append(f"- No products found in {wo['category']}; ask the seller to list products in this category.")
    else:
        lines.append(f"- {wo['category']}: {c['in_category']} products listed, {c['live']} live in the campaign, {c['pending']} pending, "
                     f"{c['addable']} not in the campaign yet")
        if c["top_live"]:
            lines.append("- Best live products by Google Ads impressions: "
                         + ", ".join(f"{r['title']} ({r['impressions']:,})" for r in c["top_live"]))
        if gmc.issues_line(c):
            lines.append(f"- Feed problems: {gmc.issues_line(c)}")
        if c["mode"] == "add_other":
            lines.append(f"- Pitch: only {c['in_category']} products in this category, so add the other ones the seller has here:")
        elif c["mode"] == "top_performers":
            basis = ("Google Ads impressions" if any(r["impressions"] for r in c["candidates"])
                     else "listing quality (none of them has Google Ads impressions yet)")
            lines.append(f"- Pitch: {c['in_category']} products in this category; add the top {len(c['candidates'])} by {basis}:")
        else:
            lines.append(f"- Pitch: every {wo['category']} product is already in the campaign. To show more often, the seller needs to "
                         f"list more {wo['category']} products on IndiaMART (about {max(1, TARGET_PRODUCTS - c['in_category'])} more).")
        for r in c["candidates"][:5]:
            lines.append(f"  - {r['title']}" + (f", {r['impressions']:,} impressions" if r["impressions"] else "")
                         + (f", INR {r['price']}" if r["price"] else "") + (f" [{', '.join(gmc.issues(r))}]" if gmc.issues(r) else ""))
    return lines + [""]


def new_campaign_lines(row, seller_wos):
    """seller.md section: new campaigns to pitch from the seller's GMC listing, and the plans."""
    news = gmc_new_campaigns(seller_wos)
    if not news:
        return []
    lines = ["## New campaigns to pitch (categories with products but no ads, from GMC)"]
    for n in news:
        demand = f", {n['market_impressions']:,} Google Ads impressions across the category" if n["market_impressions"] else ""
        lines.append(f"- {n['name']}: {n['products']} products listed{demand}. Best products: {', '.join(n['top'])}")
    lines += [f"- Plans: {row['plan_options']}", ""]
    return lines


def history_line(e):
    """One short line per past event, keeping the decision, objection and promise."""
    d, day = e["data"], e["at"][:10]
    if e["type"] == "outcome":
        parts = [d.get("call_outcome"), d.get("objection") and f"objection: {d['objection']}",
                 d.get("seller_plan") and f"plan: {d['seller_plan']}", d.get("next_step") and f"next: {d['next_step']}"]
        return f"{day} call ({d.get('channel') or 'voice'}): " + ("; ".join(p for p in parts if p) or "outcome not extracted, see transcript")
    if e["type"] == "whatsapp_in":
        return f"{day} WhatsApp from seller: {d.get('text', '')[:120]}"
    if e["type"] == "whatsapp_out":
        return f"{day} WhatsApp sent: {d.get('summary') or d.get('text', '')[:120]}"
    if e["type"] == "callback":
        return f"{day} callback booked: {d.get('time') or 'time not given'} ({d.get('reason', '')})"
    if e["type"] == "products_added":
        return f"{day} added {d.get('added')} products to {d.get('category')} (now {d.get('new_count')})"
    if e["type"] == "renewal_link":
        return f"{day} renewal link sent for {d.get('category')} ({d.get('plan')} plan)"
    if e["type"] == "quote":
        return f"{day} quote sent for {d.get('category')}"
    return None


_cache = {}


def dataset():
    """Work orders, PMCAT tree and work orders per seller, loaded once per process."""
    if not _cache:
        wos = load_work_orders()
        by_seller = defaultdict(list)
        for w in wos:
            by_seller[w["seller_id"]].append(w)
        _cache.update(wos=wos, tree=pmcat_tree(wos), by_seller=by_seller)
    return _cache


def seller_work_orders(glid):
    return dataset()["by_seller"].get(glid, [])


def effective_product_count(wo, history):
    """Products in the campaign plus those added on earlier calls (the mock count is capped at the target)."""
    added = sum(e["data"].get("added", 0) for e in history
                if e["type"] == "products_added" and e["data"].get("work_order") == wo["work_order"])
    return product_count(wo) + added if gmc_campaign(wo) else min(TARGET_PRODUCTS, product_count(wo) + added)


def products_to_add(wo, history):
    """What to pitch adding: the GMC pitch (all other products, or the top 3 by impressions) minus anything already
    added; without GMC data, mock suggestions up to the 10-product target."""
    if gmc_campaign(wo):
        done = {n for e in history if e["type"] == "products_added" and e["data"].get("work_order") == wo["work_order"]
                for n in e["data"].get("products", [])}
        return [n for n in product_suggestions(wo) if n not in done]
    return product_suggestions(wo)[: max(0, TARGET_PRODUCTS - effective_product_count(wo, history))]


def seller_row(glid, history=(), phone=""):
    """Everything VANI needs for one seller's call, or None if no rule fires for them."""
    history = list(history)
    seller_wos = seller_work_orders(glid)
    hits = [(r, w) for w in seller_wos if (r := reason_for(w))]
    if not hits:
        return None
    reason, wo = pick_primary(hits)
    tier, (up_cat, up_leads) = upsell_for(wo, seller_wos, dataset()["tree"])
    price = TIER_PRICE.get(wo["tier"], 15000)
    count = effective_product_count(wo, history)
    products = products_to_add(wo, history)
    row = {
        "phone_number": phone,
        "glid": glid,
        "seller_name": wo["seller_name"],
        "call_reason": reason,
        "work_order": wo["work_order"],
        "category": wo["category"],
        "parent_category": wo["pmcat_name"],
        "lead_count": wo["lead_count"],
        "leads_delivered": wo["delivered"],
        "delivery_pct": wo["delivery_pct"],
        "leads_28d": wo["leads_28d"],
        "delivery_28d_pct": wo["delivery_28d_pct"],
        "plan_price": price,
        "smaller_plan_leads": round(wo["lead_count"] * 0.6),
        "smaller_plan_price": round(price * 0.62 / 100) * 100,
        "product_count": count,
        "suggested_products": ", ".join(map(spoken_title, products[:3])),
        "suggested_product_count": len(products),
        "upsell_category": up_cat,
        "upsell_organic_leads": round(up_leads),
        "upsell_tier": tier,
        "other_triggers": "; ".join(f"{r}: {w['category']}" for r, w in hits if w is not wo),
        "gmc_issues": gmc.issues_line(c) if (c := gmc_campaign(wo)) else "",
        "other_campaigns": "",
        "plan_options": plan_options(wo["tier"]),
    }
    news = gmc_new_campaigns(seller_wos)
    if news:
        row["other_campaigns"] = "; ".join(f"{n['name']} ({n['products']} products listed)" for n in news)
        if reason == "upsell" and not up_cat:  # no lead-report pick: pitch the best GMC category instead
            up_cat = row["upsell_category"] = news[0]["name"]
            row["upsell_tier"] = "GMC"
    row["opening_line"] = opening_line(wo["seller_name"], reason, wo, up_cat, last_call(history))
    row["seller_md"] = seller_md(row, wo, seller_wos, history)
    return row


def build_rows(phone="", history_by_glid=None):
    """One row per seller to call, most urgent first."""
    history_by_glid = history_by_glid or {}
    rows = [r for glid in dataset()["by_seller"] if (r := seller_row(glid, history_by_glid.get(glid, []), phone))]
    return sorted(rows, key=lambda r: (PRIORITY[r["call_reason"]], r["seller_name"] or "~"))

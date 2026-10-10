"""Tools shared by the voice agent (as Sarvam API tools) and the WhatsApp bot (as LLM tools).

Each tool takes the seller's glid plus a few optional fields and returns a dict with a short
`summary` the agent can read out. Actions are recorded in the call history; payment links and
campaign edits are MOCK until real IndiaMART APIs are connected.
"""

from . import store
from .core import TARGET_PRODUCTS, effective_product_count, gmc_campaign, gmc_new_campaigns, pick_primary, products_to_add, reason_for, seller_row, seller_work_orders


def _primary(glid):
    hits = [(r, w) for w in seller_work_orders(glid) if (r := reason_for(w))]
    return pick_primary(hits)[1] if hits else seller_work_orders(glid)[0]


def _whatsapp(glid, text, summary):
    """Messages sent 'on WhatsApp' show up in the seller's chat thread (see /whatsapp/<glid>)."""
    store.record(glid, "whatsapp_out", {"text": text, "summary": summary, "channel": "system"})


def get_seller_context(glid, **_):
    return seller_row(glid, store.history(glid)) or {"error": "no call trigger for this seller"}


def get_package_status(glid, **_):
    row = seller_row(glid, store.history(glid))
    return {
        "category": row["category"],
        "leads_delivered": row["leads_delivered"],
        "lead_count": row["lead_count"],
        "delivery_pct": row["delivery_pct"],
        "leads_28d": row["leads_28d"],
        "plan_price": row["plan_price"],
        "smaller_plan_leads": row["smaller_plan_leads"],
        "smaller_plan_price": row["smaller_plan_price"],
        "summary": (f"{row['category']}: {row['leads_delivered']} of {row['lead_count']} leads delivered ({row['delivery_pct']}%). "
                    f"Same plan: {row['plan_price']} rupees for {row['lead_count']} leads. "
                    f"Smaller option: {row['smaller_plan_price']} rupees for {row['smaller_plan_leads']} leads."),
    }


def create_renewal_link(glid, plan="same", **_):
    plan = "smaller" if str(plan).lower().startswith("small") else "same"
    row = seller_row(glid, store.history(glid))
    price = row["smaller_plan_price"] if plan == "smaller" else row["plan_price"]
    leads = row["smaller_plan_leads"] if plan == "smaller" else row["lead_count"]
    link = f"https://pay.indiamart.com/renew/{row['work_order']}?plan={plan}"  # MOCK
    store.record(glid, "renewal_link", {"category": row["category"], "plan": plan, "price": price, "link": link})
    _whatsapp(glid, f"Namaste! Aapke {row['category']} Ads ka renewal: {leads} leads, ₹{price:,}. Pay karne ke liye: {link}",
              f"renewal link for {row['category']} ({plan} plan, ₹{price:,})")
    return {"link": link, "price": price, "sent_on_whatsapp": True,
            "summary": f"Renewal link for {row['category']} ({plan} plan, {price} rupees) sent on WhatsApp."}


def get_upsell_candidates(glid, **_):
    row = seller_row(glid, store.history(glid))
    news = gmc_new_campaigns(seller_work_orders(glid))
    extra = ""
    if news:
        extra = " Other categories where the seller lists products but runs no ads: " + "; ".join(
            f"{n['name']} ({n['products']} products" + (f", {n['market_impressions']:,} Google impressions in the category" if n["market_impressions"] else "")
            + ")" for n in news) + "."
    plans = f" Plans: {row['plan_options']}."
    if not row["upsell_category"]:
        return {"upsell_category": "", "other_campaigns": row["other_campaigns"], "plan_options": row["plan_options"],
                "summary": "No qualifying new category. Do not pitch a new category." + plans}
    if row["upsell_tier"] == "GMC":
        top = news[0]
        lead = (f"Pitch a new campaign for {top['name']}: the seller already lists {top['products']} products there "
                f"(best: {', '.join(top['top'])}) but runs no ads for it"
                + (f", and the category gets {top['market_impressions']:,} Google Ads impressions." if top["market_impressions"] else "."))
    else:
        where = (f"same parent category ({row['parent_category']})" if row["upsell_tier"] == "A"
                 else "a category the seller already deals in")
        lead = f"Pitch {row['upsell_category']}: about {row['upsell_organic_leads']} buyer enquiries per month, {where}."
    return {"upsell_category": row["upsell_category"], "upsell_organic_leads": row["upsell_organic_leads"], "tier": row["upsell_tier"],
            "other_campaigns": row["other_campaigns"], "plan_options": row["plan_options"], "summary": lead + extra + plans}


def send_quote(glid, category="", **_):
    row = seller_row(glid, store.history(glid))
    category = category or row["upsell_category"] or row["category"]
    price = row["plan_price"]  # MOCK: same tier price for the new category
    store.record(glid, "quote", {"category": category, "price": price})
    _whatsapp(glid, f"Namaste! {category} ke liye IndiaMART Ads quote: {row['lead_count']} leads, ₹{price:,}. "
                    f"Har mahine lagbhag {row['upsell_organic_leads'] or 'kai'} buyers yeh dhoondhte hain.",
              f"quote for {category} (₹{price:,})")
    return {"sent_on_whatsapp": True, "summary": f"Quote for {category} sent on WhatsApp."}


def get_peer_top_products(glid, **_):
    row = seller_row(glid, store.history(glid))
    c = gmc_campaign(_primary(glid))
    if c and c["mode"] != "list_more":  # real GMC listing + product ads impressions
        names = [r["title"] for r in c["candidates"][:3]]
        if c["mode"] == "top_performers":
            why = ", ".join(f"{r['title']} ({r['impressions']:,} Google impressions)" if r["impressions"] else r["title"]
                            for r in c["candidates"])
            basis = "Google Ads impressions" if any(r["impressions"] for r in c["candidates"]) else "listing quality"
            summary = (f"{row['category']} has {c['live']} products in the campaign. Of the seller's products not in it yet, "
                       f"the top {len(names)} by {basis} are: {why}. Pitch adding these.")
        else:
            summary = (f"Only {c['in_category']} {row['category']} products are listed and {c['live']} are in the campaign. "
                       f"The seller has {len(c['candidates'])} more here to add: {', '.join(names)}"
                       + (" and others" if len(c["candidates"]) > 3 else "") + ".")
        return {"current_product_count": c["live"], "suggested_count": len(c["candidates"]), "top_three": ", ".join(names),
                "pitch": c["mode"], "gmc_issues": row["gmc_issues"],
                "summary": summary + (f" Feed problems to fix: {row['gmc_issues']}." if row["gmc_issues"] else "")}
    if not row["suggested_product_count"] and row["product_count"] < TARGET_PRODUCTS:
        return {"suggested_count": 0, "current_product_count": row["product_count"], "gmc_issues": row["gmc_issues"],
                "summary": (f"All {row['product_count']} {row['category']} products are already in the campaign. Ask the seller to list "
                            f"about {TARGET_PRODUCTS - row['product_count']} more {row['category']} products on IndiaMART, "
                            "with price and photos, so the ads show more often.")}
    if not row["suggested_product_count"]:
        return {"suggested_count": 0, "current_product_count": row["product_count"],
                "summary": f"Campaign already has {row['product_count']} products. Focus on replying fast and updating prices and photos."}
    return {"current_product_count": row["product_count"], "suggested_count": row["suggested_product_count"], "top_three": row["suggested_products"],
            "gmc_issues": row["gmc_issues"],
            "summary": (f"Campaign has only {row['product_count']} products. Suggest adding {row['suggested_product_count']}; "
                        f"top ones: {row['suggested_products']}." + (f" Feed problems to fix: {row['gmc_issues']}." if row["gmc_issues"] else ""))}


def add_products_to_campaign(glid, **_):
    wo = _primary(glid)
    history = store.history(glid)
    before = effective_product_count(wo, history)
    names = products_to_add(wo, history)
    if not names:
        return {"new_product_count": before, "summary": f"Campaign already has {before} products and there are none to add."}
    store.record(glid, "products_added", {"work_order": wo["work_order"], "category": wo["category"], "added": len(names),
                                          "new_count": before + len(names), "products": names})
    _whatsapp(glid, f"{wo['category']} campaign mein yeh products add ho gaye: " + ", ".join(names),
              f"list of {len(names)} products added to {wo['category']}")
    return {"new_product_count": before + len(names),
            "summary": f"Added {len(names)} products. {wo['category']} campaign now has {before + len(names)} products. Full list sent on WhatsApp."}


def schedule_callback(glid, time="", reason="", transcript="", **_):
    store.record(glid, "callback", {"time": time, "reason": reason, "transcript_tail": (transcript or "")[-400:]})
    return {"scheduled": True, "summary": f"Callback scheduled{f' for {time}' if time else ''}."}


def send_whatsapp(glid, message="", **_):
    _whatsapp(glid, message, message[:120])
    return {"sent": True, "summary": "WhatsApp message sent."}


OUTCOME_FIELDS = ("call_outcome", "renewal_plan", "objection", "seller_plan", "callback_time", "whatsapp_to_send", "next_step")


def log_outcome(glid, channel="voice", interaction_id="", transcript="", summary="", **fields):
    """Save a call's result with its full transcript; the next call and WhatsApp chat read it back via seller.md."""
    data = {k: fields.get(k) for k in OUTCOME_FIELDS if fields.get(k) and fields.get(k) != "none"}
    data.update(channel=channel, interaction_id=interaction_id, summary=(summary or "").strip(), transcript=(transcript or "").strip())
    store.record(glid, "outcome", data)
    return {"logged": True}


TOOLS = {f.__name__: f for f in (get_seller_context, get_package_status, create_renewal_link, get_upsell_candidates, send_quote,
                                 get_peer_top_products, add_products_to_campaign, schedule_callback, send_whatsapp, log_outcome)}


def run(name, glid, args):
    if name not in TOOLS:
        return {"error": f"unknown tool {name}"}
    if not seller_work_orders(glid):
        return {"error": "unknown glid", "summary": "Seller not found. Do not quote any numbers."}
    return TOOLS[name](glid, **{k: v for k, v in args.items() if k != "glid"})


# OpenAI-style tool specs for the WhatsApp bot (glid is filled in by the server, not the model).
def _spec(name, description, **props):
    return {"type": "function", "function": {"name": name, "description": description, "parameters": {
        "type": "object", "properties": {k: {"type": "string", "description": d} for k, d in props.items()}, "required": []}}}


CHAT_TOOL_SPECS = [
    _spec("get_package_status", "Current package delivery and renewal prices. Call before quoting any price."),
    _spec("create_renewal_link", "Create the renewal payment link and send it. Only after the seller agrees to renew.",
          plan="'same' or 'smaller'"),
    _spec("get_upsell_candidates", "The one best new category to offer, with its monthly buyer demand."),
    _spec("send_quote", "Send a price quote for a new category.", category="category name"),
    _spec("get_peer_top_products", "Best products to add to an under-delivering campaign."),
    _spec("add_products_to_campaign", "Add the suggested products to the campaign. Only after a clear yes."),
    _spec("schedule_callback", "Book a call from VANI or an executive.", time="when the seller wants the call", reason="why"),
]

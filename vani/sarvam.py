"""Talking to Sarvam: start an outbound VANI call, and run the WhatsApp bot on sarvam-105b."""

import json
import os
import urllib.error
import urllib.request

from sarvamai import SarvamAI

from . import store, tools
from .core import seller_row

CHAT_MODEL = "sarvam-105b"


def env(name, default=""):
    return os.environ.get(name, default).strip()


# --- Outbound call ------------------------------------------------------------------------
CALL_ENV = ("SARVAM_AGENT_API_KEY", "SARVAM_ORG_ID", "SARVAM_WORKSPACE_ID", "SARVAM_APP_ID", "SARVAM_APP_VERSION",
            "SARVAM_CONNECTION_ID", "SARVAM_AGENT_PHONE")


def agent_key():
    """Voice agents (indus.sarvam.ai → Settings → API keys) use their own key; the sk_ key only works for chat."""
    return env("SARVAM_AGENT_API_KEY") or env("SARVAM_API_KEY")


def missing_call_config():
    return [k for k in CALL_ENV if not (agent_key() if k == "SARVAM_AGENT_API_KEY" else env(k))]


def place_call(glid, phone):
    """Dial `phone` with VANI, preloaded with this seller's context. Returns Sarvam's attempt id."""
    if missing_call_config():
        raise ValueError(f"calling needs {', '.join(missing_call_config())} in .env")
    if not phone:
        raise ValueError("enter the number to call")
    row = seller_row(glid, store.history(glid))
    if not row:
        raise ValueError("no call trigger for this seller")
    variables = {k: str(v) for k, v in row.items() if k != "phone_number"}
    body = {
        "app_config": {
            "app_id": env("SARVAM_APP_ID"),
            "app_version": int(env("SARVAM_APP_VERSION")),
            "connection_config": {"connection_id": env("SARVAM_CONNECTION_ID"), "agent_phone_number": env("SARVAM_AGENT_PHONE")},
            "agent_variables": variables,
            "app_overrides": {"initial_bot_message": row["opening_line"]},
        },
        "user_config": {"user_phone_number": phone},
    }
    if env("PUBLIC_URL"):
        hook = f"{env('PUBLIC_URL').rstrip('/')}/webhooks/sarvam?token={env('TOOLS_TOKEN')}"
        body["webhook_config"] = {"url": hook, "metadata": {"glid": glid}}

    url = f"https://apps.sarvam.ai/api/outbounds/v1/orgs/{env('SARVAM_ORG_ID')}/workspaces/{env('SARVAM_WORKSPACE_ID')}/outbounds"
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "X-API-Key": agent_key()})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            result = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Sarvam outbound API {e.code}: {e.read().decode(errors='replace')[:300]}") from e
    store.record(glid, "call_placed", {"phone": phone[:-4] + "XXXX", "attempt_id": result.get("attempt_id"), "reason": row["call_reason"]})
    return result


# --- WhatsApp bot (same context + same tools as the voice agent) -----------------------------
WHATSAPP_PROMPT = """You are VANI, IndiaMART's assistant (female: use feminine Hindi forms like "bhej deti hoon"), chatting on WhatsApp with a seller who pays for IndiaMART Ads (IM Ad Pro).
This chat continues earlier conversations: read the History and Last conversation sections first and pick up from them. Never ask what is already answered there.

{seller_md}

Facts for this seller: call reason {call_reason}; category {category}; {leads_delivered} of {lead_count} leads delivered ({delivery_pct}%);
last 28 days {leads_28d} leads; same plan {plan_price} rupees, smaller plan {smaller_plan_price} rupees for {smaller_plan_leads} leads;
upsell category: {upsell_category} ({upsell_organic_leads} buyer enquiries/month); campaign products: {product_count}.

Rules:
- Short WhatsApp-style replies (1-3 lines), in the seller's language (Hinglish by default).
- Prices and numbers only from the facts above or tool results. Never invent discounts.
- Use tools to act: renewal link, quote, add products (only after a clear yes), callback.
- If the seller wants a human, book a callback."""


def _client():
    return SarvamAI(api_subscription_key=env("SARVAM_API_KEY"))


def whatsapp_thread(glid):
    """Chat messages for a seller, oldest first: seller messages, bot replies, and links/quotes sent from calls."""
    return [e for e in reversed(store.history(glid, limit=200)) if e["type"] in ("whatsapp_in", "whatsapp_out")]


def whatsapp_reply(glid, text):
    store.record(glid, "whatsapp_in", {"text": text})
    row = seller_row(glid, store.history(glid))
    if not row:
        reply = "Namaste! Aapki kya madad kar sakte hain?"
        store.record(glid, "whatsapp_out", {"text": reply, "channel": "bot"})
        return reply

    messages = [{"role": "system", "content": WHATSAPP_PROMPT.format(**row)}]
    for e in whatsapp_thread(glid)[-20:]:
        messages.append({"role": "user" if e["type"] == "whatsapp_in" else "assistant", "content": e["data"]["text"]})

    client = _client()
    for _ in range(4):  # model -> tool calls -> model, at most a few rounds
        msg = client.chat.completions(model=CHAT_MODEL, messages=messages, tools=tools.CHAT_TOOL_SPECS,
                                      temperature=0.3, reasoning_effort="low", max_tokens=8192).choices[0].message
        calls = getattr(msg, "tool_calls", None) or []
        if not calls:
            break
        messages.append({"role": "assistant", "content": msg.content or "",
                         "tool_calls": [{"id": c.id, "type": "function",
                                         "function": {"name": c.function.name, "arguments": c.function.arguments}} for c in calls]})
        for c in calls:
            args = json.loads(c.function.arguments or "{}")
            result = tools.run(c.function.name, glid, args)
            messages.append({"role": "tool", "tool_call_id": c.id, "content": json.dumps(result, ensure_ascii=False)})

    reply = (msg.content or "").strip() or "Ji, main check karke batati hoon."
    store.record(glid, "whatsapp_out", {"text": reply, "channel": "bot"})
    return reply


# --- Browser test calls: outcome extraction ------------------------------------------------
# Browser sessions don't get Sarvam's end-of-call webhook, so we extract the same output
# variables from the transcript ourselves and log them like a phone call.
EXTRACT_PROMPT = """Read this call transcript between VANI (IndiaMART's voice agent) and a seller, and return only a JSON object with:
call_outcome: one of renewal_agreed, renewal_declined, upsell_interested, upsell_declined, products_approved, improve_declined, callback_requested, wrong_person_or_busy, do_not_call, other
renewal_plan: same, smaller or none
objection: the seller's main objection in one short line, or ""
seller_plan: if the seller declined to renew, their plan with IndiaMART now, in one line, or ""
callback_time: when a callback was agreed, as the seller said it, or ""
whatsapp_to_send: renewal_link, upsell_quote, product_list or none
next_step: the agreed next step in one line
summary: 2-3 plain sentences on what was discussed, what the seller said (reasons, numbers, promises) and what was agreed, so the next caller can continue"""


def extract_outcome(transcript):
    msg = _client().chat.completions(
        model=CHAT_MODEL, temperature=0, reasoning_effort="low", max_tokens=8192,
        messages=[{"role": "system", "content": EXTRACT_PROMPT}, {"role": "user", "content": transcript}],
    ).choices[0].message
    text = (msg.content or "").strip()
    start, end = text.find("{"), text.rfind("}")
    try:
        return json.loads(text[start:end + 1]) if start != -1 else {}
    except json.JSONDecodeError:
        return {}

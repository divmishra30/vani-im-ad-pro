"""VANI backend: call queue dashboard, Sarvam tools/hooks, outbound calls, WhatsApp follow-up.

Run locally:  uvicorn server:app --reload --port 8000
Env (.env):   SARVAM_API_KEY, TOOLS_TOKEN, DASHBOARD_PASSWORD, PUBLIC_URL,
              SARVAM_ORG_ID, SARVAM_WORKSPACE_ID, SARVAM_APP_ID, SARVAM_APP_VERSION,
              SARVAM_CONNECTION_ID, SARVAM_AGENT_PHONE   (the last six only for "Call now")
"""

import base64
import csv
import io
import json
import os
import secrets
import time
import urllib.error
import urllib.request
from html import escape
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv, set_key
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(ENV_PATH)

from vani import gmc, sarvam, store, tools  # noqa: E402  (after load_dotenv so env is set)
from vani.core import (DEMO_SELLERS, PRIORITY, build_rows, gmc_campaign, pick_primary, reason_for,  # noqa: E402
                       seller_row, seller_work_orders)

app = FastAPI(title="VANI · IM Ad Pro")
PUBLIC_PATHS = ("/tools/", "/webhooks/", "/health")


@app.middleware("http")
async def dashboard_auth(request: Request, call_next):
    """Basic auth on the dashboard (seller data); tools and webhooks use the TOOLS_TOKEN instead."""
    password = sarvam.env("DASHBOARD_PASSWORD")
    if password and not request.url.path.startswith(PUBLIC_PATHS):
        sent = request.headers.get("authorization", "")
        ok = sent.startswith("Basic ") and secrets.compare_digest(
            base64.b64decode(sent[6:]).decode(errors="ignore").partition(":")[2], password)
        if not ok:
            return Response("Login required", status_code=401, headers={"WWW-Authenticate": 'Basic realm="VANI"'})
    return await call_next(request)


def token_ok(request: Request):
    token = sarvam.env("TOOLS_TOKEN")
    sent = request.headers.get("authorization", "").removeprefix("Bearer ").strip() or request.query_params.get("token", "")
    return not token or secrets.compare_digest(sent, token)


# --- Tools and hooks for the Sarvam agent ---------------------------------------------------
@app.post("/tools/{name}")
@app.get("/tools/{name}")
async def tool(name: str, request: Request):
    if not token_ok(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    args = dict(request.query_params)
    if request.method == "POST":
        try:
            body = await request.json()
            args.update({k: v for k, v in body.items() if v is not None} if isinstance(body, dict) else {})
        except (json.JSONDecodeError, UnicodeDecodeError):
            args.update(dict(await request.form()))
    args.pop("token", None)
    result = tools.run(name, str(args.get("glid", "")).strip(), args)
    return JSONResponse(result, status_code=404 if "error" in result else 200)


@app.post("/webhooks/sarvam")
async def sarvam_webhook(request: Request):
    """End-of-call webhook (instant outbound or campaign): save outcome variables + transcript."""
    if not token_ok(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    p = await request.json()
    final = p.get("final_agent_variables") or {}
    glid = str(((p.get("webhook_config") or {}).get("metadata") or {}).get("glid") or final.get("glid") or "")
    if not seller_work_orders(glid):
        return {"ignored": "no glid"}
    transcript = "\n".join(f"{'Seller' if t.get('role') == 'user' else 'VANI'}: {t.get('en_text')}"
                           for t in p.get("interaction_transcript") or [] if t.get("en_text"))
    if p.get("status") != "connected":
        store.record(glid, "call_not_connected", {"status": p.get("status"), "reason": p.get("failure_reason")})
    else:
        try:  # Sarvam fills the outcome variables; we add a summary (and fill any gaps) from the transcript
            extracted = sarvam.extract_outcome(transcript) if transcript else {}
        except Exception:
            extracted = {}
        tools.log_outcome(glid, channel="phone call", interaction_id=p.get("interaction_id") or "", transcript=transcript,
                          summary=extracted.get("summary", ""),
                          **{k: final.get(k) or extracted.get(k) for k in tools.OUTCOME_FIELDS})
    return {"ok": True}


@app.get("/health")
def health():
    return {"ok": True}


# --- Dashboard ------------------------------------------------------------------------------
CSS = """
:root{--bg:#f4f6fb;--card:#fff;--line:#e6e9f0;--ink:#0f172a;--ink2:#475467;--ink3:#98a2b3;--brand:#2f3fbf;--brand2:#4f5fe8;
--renew:#d92d20;--renew-bg:#fef3f2;--upsell:#079455;--upsell-bg:#ecfdf3;--improve:#dc6803;--improve-bg:#fffaeb;--r:14px}
*{box-sizing:border-box}html,body{margin:0}body{font:14px/1.5 Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;background:var(--bg);color:var(--ink);-webkit-font-smoothing:antialiased}
a{color:var(--brand);text-decoration:none}a:hover{text-decoration:underline}
.app{display:grid;grid-template-columns:232px 1fr;min-height:100vh}
nav.side{background:#0b1240;color:#c7cdf5;padding:22px 14px;position:sticky;top:0;height:100vh;display:flex;flex-direction:column;gap:4px}
.logo{display:flex;align-items:center;gap:10px;padding:0 10px 22px;color:#fff}
.logo .mark{width:36px;height:36px;border-radius:11px;background:linear-gradient(135deg,#6d7cff,#2f3fbf);display:grid;place-items:center;font-weight:800;box-shadow:0 6px 18px #4f5fe866}
.logo b{display:block;font-size:16px;letter-spacing:.3px}.logo small{color:#8f98d8;font-size:11.5px}
nav.side a{display:flex;align-items:center;gap:10px;padding:9px 12px;border-radius:10px;color:#c7cdf5;font-weight:500}
nav.side a:hover{background:#ffffff12;text-decoration:none}nav.side a.on{background:#ffffff1c;color:#fff}
nav.side svg{width:18px;height:18px;flex:none}
.side-foot{margin-top:auto;padding:12px;border-radius:12px;background:#ffffff0d;font-size:12px;line-height:1.45}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px;background:#f79009}.dot.ok{background:#17b26a}
main{padding:28px 36px 80px;max-width:1440px;width:100%}
.top{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;margin-bottom:22px;flex-wrap:wrap}
h1{font-size:24px;line-height:1.2;margin:0;letter-spacing:-.4px}h2{font-size:15px;margin:0 0 12px}
.sub{color:var(--ink2);margin-top:6px}.muted{color:var(--ink3)}.small{font-size:12px}
.crumb{font-size:13px;color:var(--ink2);margin-bottom:10px;display:inline-block}
.card{background:var(--card);border:1px solid var(--line);border-radius:var(--r);padding:18px 20px;box-shadow:0 1px 2px #1018280a}
.kpis{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:14px;margin-bottom:20px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:var(--r);padding:16px 18px;cursor:pointer;transition:.15s;position:relative;overflow:hidden;text-align:left;font:inherit;color:inherit}
.kpi:hover{border-color:#c5cae0;box-shadow:0 6px 20px #10182812}.kpi.on{border-color:var(--brand);box-shadow:0 0 0 3px #2f3fbf22}
.kpi .n{font-size:28px;font-weight:700;letter-spacing:-.6px;line-height:1.1;margin:6px 0 2px}.kpi .l{font-weight:600;font-size:13px}
.kpi .h{font-size:12px;color:var(--ink3)}.kpi:before{content:"";position:absolute;left:0;top:0;bottom:0;width:4px;background:var(--c,var(--brand))}
.kpi.renew{--c:var(--renew)}.kpi.upsell{--c:var(--upsell)}.kpi.improve{--c:var(--improve)}.kpi.done{--c:#7a5af8;cursor:default}
.toolbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding:12px 14px;border-bottom:1px solid var(--line)}
.search{display:flex;align-items:center;gap:8px;background:#f8f9fc;border:1px solid var(--line);border-radius:10px;padding:0 12px;flex:1;max-width:380px}
.search svg{width:16px;height:16px;color:var(--ink3)}.search input{border:0;background:transparent;outline:0;padding:9px 0;width:100%;font:inherit}
.seg{display:inline-flex;background:#f1f3f8;border-radius:10px;padding:3px}
.seg button{border:0;background:transparent;padding:6px 12px;border-radius:8px;font:inherit;font-weight:500;color:var(--ink2);cursor:pointer}
.seg button.on{background:#fff;color:var(--ink);box-shadow:0 1px 3px #10182822}
.count{margin-left:auto;color:var(--ink3);font-size:13px}
.tbl{width:100%;border-collapse:separate;border-spacing:0}
.tbl th{position:sticky;top:0;background:#fafbfd;font-size:11.5px;font-weight:600;text-transform:uppercase;letter-spacing:.4px;color:var(--ink3);text-align:left;padding:10px 14px;border-bottom:1px solid var(--line);z-index:1}
.tbl td{padding:13px 14px;border-bottom:1px solid #f0f2f6;vertical-align:middle}
.tbl tr.row{cursor:pointer;transition:background .1s}.tbl tr.row:hover td{background:#f8f9ff}
.who{display:flex;gap:12px;align-items:center;min-width:220px}
.av{width:38px;height:38px;border-radius:12px;display:grid;place-items:center;font-weight:700;font-size:13px;flex:none;color:#fff}
.av.renew{background:linear-gradient(135deg,#f97066,#d92d20)}.av.upsell{background:linear-gradient(135deg,#47cd89,#079455)}.av.improve{background:linear-gradient(135deg,#fdb022,#dc6803)}
.who b{display:block;font-weight:600;max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.badge{display:inline-flex;align-items:center;gap:5px;padding:2px 9px;border-radius:999px;font-size:12px;font-weight:600;white-space:nowrap}
.badge.renew{color:var(--renew);background:var(--renew-bg)}.badge.upsell{color:var(--upsell);background:var(--upsell-bg)}.badge.improve{color:var(--improve);background:var(--improve-bg)}
.badge.demo{color:#6941c6;background:#f4f3ff;font-size:11px;padding:1px 7px}
.badge.good{color:#067647;background:#dcfae6}.badge.bad{color:#b42318;background:#fee4e2}.badge.neutral{color:#344054;background:#f2f4f7}.badge.new{color:var(--ink3);background:#f8f9fc;font-weight:500}
.bar{height:6px;border-radius:99px;background:#eef0f5;overflow:hidden;width:110px;margin-top:5px}.bar i{display:block;height:100%;border-radius:99px;background:var(--brand2)}
.bar i.hi{background:#d92d20}.bar i.mid{background:#17b26a}.bar i.lo{background:#f79009}
.pct{font-weight:600;font-variant-numeric:tabular-nums}.cat b{font-weight:500}
.pitch{max-width:300px;color:var(--ink2);font-size:13px}
.btn{display:inline-flex;align-items:center;gap:7px;border:0;border-radius:10px;padding:8px 14px;font:inherit;font-weight:600;cursor:pointer;background:var(--brand);color:#fff;white-space:nowrap;transition:.15s;text-decoration:none!important}
.btn:hover{background:#2532a8}.btn svg{width:16px;height:16px}.btn.sm{padding:6px 11px;font-size:13px;border-radius:9px}
.btn.ghost{background:#fff;color:var(--ink);border:1px solid var(--line)}.btn.ghost:hover{background:#f8f9fc}
.btn.green{background:#079455}.btn.green:hover{background:#067647}.btn.red{background:#d92d20}.btn.red:hover{background:#b42318}
.btn:disabled{opacity:.45;cursor:not-allowed}
.empty{padding:40px;text-align:center;color:var(--ink3)}
.notice{display:flex;gap:12px;align-items:center;padding:12px 16px;border-radius:12px;margin-bottom:18px;background:#fffaeb;border:1px solid #fedf89;color:#93370d}
.notice.ok{background:#ecfdf3;border-color:#abefc6;color:#067647}.notice.err{background:#fef3f2;border-color:#fecdca;color:#b42318}
.notice a{color:inherit;font-weight:600;text-decoration:underline}
.grid2{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(0,1fr);gap:18px;align-items:start}
.stack{display:flex;flex-direction:column;gap:18px}
.hero{display:flex;gap:18px;align-items:center;flex-wrap:wrap}.hero .av{width:56px;height:56px;border-radius:16px;font-size:18px}
.hero h1{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.hero .actions{margin-left:auto;display:flex;gap:10px}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:0;margin-top:18px;border-top:1px solid var(--line);padding-top:16px}
.stats>div{padding:0 16px;border-left:1px solid var(--line)}.stats>div:first-child{padding-left:0;border:0}
.stats .v{font-size:20px;font-weight:700;letter-spacing:-.3px}.stats .k{font-size:12px;color:var(--ink3)}
.quote{background:linear-gradient(135deg,#eef0ff,#f7f8ff);border:1px solid #dfe3ff;border-radius:12px;padding:14px 16px;font-size:14.5px;color:#1e2a78}
.quote:before{content:"VANI opens with";display:block;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:#6b75c9;margin-bottom:4px}
.kv{display:grid;grid-template-columns:150px 1fr;gap:8px 14px;font-size:13.5px}.kv dt{color:var(--ink3)}.kv dd{margin:0}
.timeline{list-style:none;margin:0;padding:0}.timeline li{display:flex;gap:12px;padding:0 0 16px;position:relative}
.timeline li:before{content:"";position:absolute;left:15px;top:30px;bottom:0;width:2px;background:var(--line)}.timeline li:last-child:before{display:none}
.ti{width:32px;height:32px;border-radius:10px;background:#f1f3f8;display:grid;place-items:center;flex:none;font-size:15px}
.timeline .t{font-weight:600}.timeline .d{color:var(--ink2);font-size:13px}
details{border:1px solid var(--line);border-radius:12px;background:#fff}details+details{margin-top:12px}
summary{cursor:pointer;padding:12px 16px;font-weight:600;list-style:none;display:flex;justify-content:space-between}summary::-webkit-details-marker{display:none}
summary:after{content:"▾";color:var(--ink3)}details[open] summary{border-bottom:1px solid var(--line)}
pre{margin:0;padding:16px;white-space:pre-wrap;font:12.5px/1.6 ui-monospace,SFMono-Regular,Consolas,monospace;color:#1f2937;background:#fafbfd;border-radius:0 0 12px 12px;max-height:520px;overflow:auto}
table.vars{width:100%;border-collapse:collapse;font-size:13px}table.vars td{padding:7px 16px;border-top:1px solid #f0f2f6;vertical-align:top}table.vars td:first-child{color:var(--ink3);width:200px;font-family:ui-monospace,Consolas,monospace;font-size:12px}
/* call card */
#callcard{position:fixed;right:24px;bottom:24px;width:400px;max-height:calc(100vh - 48px);display:none;flex-direction:column;background:#fff;border-radius:20px;box-shadow:0 24px 60px #0b124055,0 0 0 1px #0b124014;overflow:hidden;z-index:50}
#callcard.on{display:flex}
.cc-top{background:radial-gradient(120% 140% at 0% 0%,#4f5fe8,#0b1240);color:#fff;padding:18px 20px;display:flex;gap:14px;align-items:center}
.pulse{width:48px;height:48px;border-radius:50%;background:#ffffff22;display:grid;place-items:center;font-weight:800;position:relative;flex:none}
.pulse.live:after{content:"";position:absolute;inset:-6px;border-radius:50%;border:2px solid #8ea0ff;animation:p 1.6s infinite}
@keyframes p{0%{transform:scale(.9);opacity:1}100%{transform:scale(1.25);opacity:0}}
.cc-top b{display:block;font-size:15px}.cc-top small{color:#c7cdf5}.cc-time{margin-left:auto;font-variant-numeric:tabular-nums;font-weight:600;font-size:15px}
.cc-state{padding:9px 20px;font-size:12.5px;color:var(--ink2);background:#f8f9fc;border-bottom:1px solid var(--line)}
.cc-chat{padding:16px;display:flex;flex-direction:column;gap:8px;overflow:auto;min-height:180px;max-height:46vh;background:#fcfcfe}
.msg{max-width:85%;padding:9px 13px;border-radius:14px;white-space:pre-wrap;font-size:13.5px;line-height:1.45}
.msg.out{align-self:flex-start;background:#eef0ff;color:#1e2a78;border-bottom-left-radius:4px}.msg.in{align-self:flex-end;background:#0b1240;color:#fff;border-bottom-right-radius:4px}
.msg small{display:block;font-size:10.5px;opacity:.6;margin-top:3px}
.cc-foot{padding:14px 16px;display:flex;gap:10px;border-top:1px solid var(--line)}.cc-foot .btn{flex:1;justify-content:center}
.convo{display:flex;flex-direction:column;gap:6px;padding:14px 16px;max-height:420px;overflow:auto;background:#fcfcfe;border-radius:0 0 12px 12px}
.convo-sum{padding:12px 16px 0;color:var(--ink2);font-size:13px}
.cc-result{margin:0 16px 14px;padding:12px 14px;border-radius:12px;background:#ecfdf3;border:1px solid #abefc6;font-size:13px;display:none}
/* whatsapp */
.phone{max-width:440px;border-radius:26px;overflow:hidden;border:1px solid var(--line);box-shadow:0 20px 50px #0b124022;background:#fff}
.phone-top{background:#075e54;color:#fff;padding:14px 18px;display:flex;gap:12px;align-items:center}.phone-top .av{width:38px;height:38px;background:#ffffff33}
.wa{background:#efeae2;padding:16px;display:flex;flex-direction:column;gap:6px;height:480px;overflow:auto}
.wa .msg.in{background:#d9fdd3;color:#111;border-radius:12px 12px 4px 12px}.wa .msg.out{background:#fff;color:#111;border-radius:12px 12px 12px 4px}
.wa-form{display:flex;gap:8px;padding:10px;background:#f0f2f5}.wa-form input{flex:1;border:0;border-radius:20px;padding:10px 14px;font:inherit;outline:0}
.wa-form button{border:0;background:#00a884;color:#fff;border-radius:50%;width:42px;height:42px;cursor:pointer;font-size:16px}
.check{display:flex;gap:10px;align-items:center;padding:10px 0;border-top:1px solid #f0f2f6}.check:first-child{border:0}.check code{font-size:12.5px}
@media(max-width:1100px){.kpis{grid-template-columns:repeat(3,1fr)}.grid2{grid-template-columns:1fr}.app{grid-template-columns:1fr}nav.side{position:static;height:auto;flex-direction:row;flex-wrap:wrap}.side-foot{display:none}}
"""

ICONS = {
    "queue": '<path d="M4 6h16M4 12h16M4 18h10"/>',
    "activity": '<path d="M3 12h4l3-8 4 16 3-8h4"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
    "phone": '<path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1 1 .4 1.9.7 2.8a2 2 0 0 1-.5 2.1L8 9.9a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.8.7a2 2 0 0 1 1.7 2z"/>',
    "chat": '<path d="M21 11.5a8.4 8.4 0 0 1-9 8.4 8.5 8.5 0 0 1-3.8-.9L3 21l1.9-5.2A8.4 8.4 0 0 1 3.9 12 8.5 8.5 0 0 1 12.4 3.5h.5a8.5 8.5 0 0 1 8.1 8z"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>',
    "download": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/>',
}


def icon(name):
    return (f'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
            f'stroke-linejoin="round">{ICONS[name]}</svg>')


TABS = {"renew": "Renew", "upsell": "Upsell", "improve": "Improve"}
RULES = {"renew": "Delivery >80% · renew the package", "upsell": "Delivery 50–80% · add a category",
         "improve": "28-day delivery <50% · fix it"}
GOOD = {"renewal_agreed", "upsell_interested", "products_approved"}
BAD = {"renewal_declined", "upsell_declined", "improve_declined", "do_not_call"}
EVENT_LOOK = {  # type -> (emoji, title)
    "outcome": ("🎯", "Call outcome"), "call_placed": ("📞", "Call placed"), "call_not_connected": ("📵", "Call not connected"),
    "whatsapp_in": ("💬", "Seller on WhatsApp"), "whatsapp_out": ("🤖", "VANI on WhatsApp"), "renewal_link": ("🔗", "Renewal link sent"),
    "quote": ("🧾", "Quote sent"), "products_added": ("📦", "Products added"), "callback": ("⏰", "Callback booked"),
}


def call_ready():
    """Missing settings for the in-browser call (empty list = ready)."""
    return [k for k in BROWSER_ENV if not (sarvam.agent_key() if k == "SARVAM_AGENT_API_KEY" else sarvam.env(k))]


def page(title, body, active=""):
    ok, _ = live_status()
    links = [("/", "queue", "Call queue"), ("/activity", "activity", "Activity"), ("/setup", "settings", "Setup")]
    nav = "".join(f'<a href="{h}" class="{"on" if active == i else ""}">{icon(i)}{t}</a>' for h, i, t in links)
    return HTMLResponse(f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{escape(title)} · VANI</title>
<meta name="viewport" content="width=device-width,initial-scale=1"><style>{CSS}</style></head>
<body><div class="app"><nav class="side"><div class="logo"><div class="mark">V</div><div><b>VANI</b><small>IM Ad Pro voice agent</small></div></div>
{nav}<div class="side-foot"><a href="/setup" style="color:inherit;padding:0;display:inline"><span class="dot {'ok' if ok else ''}"></span>{'Agent connected' if ok else 'Agent not connected · fix'}</a>
<div class="muted" style="margin-top:4px">Sarvam app {escape(sarvam.env('SARVAM_APP_ID') or '—')} · v{escape(sarvam.env('SARVAM_APP_VERSION') or '—')}</div></div></nav>
<main>{body}</main></div></body></html>""")


def setup_notice(missing):
    return (f'<div class="notice">⚠️ Calling isn&#39;t ready: {", ".join(missing)} missing. <a href="/setup">Open setup</a></div>'
            if missing else "")


def flash(request):
    msg, err = request.query_params.get("msg"), request.query_params.get("err")
    return (f'<div class="notice ok">{escape(msg)}</div>' if msg else "") + (f'<div class="notice err">{escape(err)}</div>' if err else "")


def initials(name):
    words = [w for w in (name or "").replace("&", " ").split() if w[:1].isalnum()]
    return ("".join(w[0] for w in words[:2]) or "?").upper()


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def bar(pct):
    p = num(pct)
    cls = "hi" if p > 80 else "mid" if p >= 50 else "lo"
    return f'<div class="bar"><i class="{cls}" style="width:{min(p, 100):.0f}%"></i></div>'


def status_badge(history):
    """The seller's latest state as a coloured chip."""
    outcome = next((e for e in history if e["type"] == "outcome"), None)
    if outcome:
        o = outcome["data"].get("call_outcome") or "other"
        cls = "good" if o in GOOD else "bad" if o in BAD else "neutral"
        return f'<span class="badge {cls}">{escape(o.replace("_", " "))}</span>'
    if history:
        return f'<span class="badge neutral">{escape(EVENT_LOOK.get(history[0]["type"], ("", history[0]["type"]))[1])}</span>'
    return '<span class="badge new">Not contacted</span>'


def _pitch(r):
    if r["call_reason"] == "renew":
        return f"Renew at ₹{int(r['plan_price']):,} · or ₹{int(r['smaller_plan_price']):,} for {r['smaller_plan_leads']} leads"
    if r["call_reason"] == "upsell":
        return (f"Add <b>{escape(r['upsell_category'])}</b> · ~{r['upsell_organic_leads']} enquiries/mo" if r["upsell_category"]
                else "No category above 200 enquiries/mo yet · review campaign")
    if int(r["suggested_product_count"] or 0):
        return f"Find the cause · add {r['suggested_product_count']} products (has {r['product_count']})"
    return f"Find the cause of low delivery · {r['product_count']} products live"


def _event_text(e):
    d = e["data"]
    if e["type"] == "outcome":
        return " · ".join(str(d[k]).replace("_", " ") for k in ("call_outcome", "objection", "seller_plan", "next_step") if d.get(k))
    return d.get("summary") or d.get("text") or " · ".join(f"{k}: {v}" for k, v in d.items() if v and k not in ("transcript_tail", "transcript"))


def conversations(history):
    """Every stored call transcript for a seller, newest first, as expandable chat logs."""
    calls = [e for e in history if e["type"] == "outcome" and e["data"].get("transcript")]
    if not calls:
        return ""
    items = []
    for i, e in enumerate(calls):
        d = e["data"]
        bubbles = []
        for line in d["transcript"].splitlines():
            who, _, text = line.partition(":")
            if not text:
                continue
            seller_side = who.strip().lower() in ("seller", "user")
            bubbles.append(f'<div class="msg {"in" if seller_side else "out"}">{escape(text.strip())}<small>{"Seller" if seller_side else "VANI"}</small></div>')
        o = d.get("call_outcome") or "other"
        cls = "good" if o in GOOD else "bad" if o in BAD else "neutral"
        items.append(f"""<details {'open' if i == 0 else ''}><summary><span>{when(e['at'])} · {escape(d.get('channel') or 'call')}
<span class="badge {cls}" style="margin-left:6px">{escape(o.replace('_', ' '))}</span></span></summary>
{f'<div class="convo-sum">{escape(d["summary"])}</div>' if d.get("summary") else ''}<div class="convo">{''.join(bubbles)}</div></details>""")
    return (f'<div class="card"><h2>Conversations ({len(calls)})</h2><p class="muted small" style="margin:-6px 0 12px">'
            f'Full transcripts. The latest one is in seller.md, so VANI continues from it on the next call.</p>{"".join(items)}</div>')


def when(at):
    return at[:16].replace("T", " ") + " UTC"


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    by_seller = store.history_by_seller()
    rows = build_rows("", by_seller)
    rows.sort(key=lambda r: (r["glid"] not in DEMO_SELLERS, PRIORITY[r["call_reason"]], -num(r["delivery_pct"])))
    contacted = sum(1 for r in rows if by_seller.get(r["glid"]))
    won = sum(1 for r in rows if any(e["type"] == "outcome" and e["data"].get("call_outcome") in GOOD for e in by_seller.get(r["glid"], [])))
    missing = call_ready()
    kpis = (f'<button class="kpi on" data-f=""><div class="l">All cases</div><div class="n">{len(rows)}</div><div class="h">one call per seller</div></button>'
            + "".join(f'<button class="kpi {k}" data-f="{k}"><div class="l">{v}</div><div class="n">{sum(r["call_reason"] == k for r in rows)}</div>'
                      f'<div class="h">{RULES[k]}</div></button>' for k, v in TABS.items())
            + f'<div class="kpi done"><div class="l">Contacted</div><div class="n">{contacted}</div><div class="h">{won} positive outcome{"s" if won != 1 else ""}</div></div>')
    trs = "".join(_case_row(r, by_seller.get(r["glid"], []), not missing) for r in rows)
    setup = setup_notice(missing)
    return page("Call queue", f"""{flash(request)}{setup}
<div class="top"><div><h1>Today's call queue</h1><div class="sub">Sellers flagged from the 9 Oct lead report. Most urgent work order per seller: renew → upsell → improve.</div></div>
<a class="btn ghost" href="/cohort.csv">{icon('download')}Campaign CSV</a></div>
<div class="kpis">{kpis}</div>
<div class="card" style="padding:0;overflow:hidden">
<div class="toolbar"><label class="search">{icon('search')}<input id="q" placeholder="Search seller, GLID or category"></label>
<div class="seg" id="status"><button class="on" data-s="">All</button><button data-s="new">Not contacted</button><button data-s="done">Contacted</button></div>
<div class="seg" id="demo"><button class="on" data-d="">Everyone</button><button data-d="1">★ Demo</button></div>
<span class="count" id="count"></span></div>
<table class="tbl"><thead><tr><th>Seller</th><th>Case</th><th>Category</th><th>Package delivery</th><th>Last 28 days</th><th>VANI will</th><th>Status</th><th></th></tr></thead>
<tbody id="rows">{trs}</tbody></table><div class="empty" id="empty" style="display:none">No sellers match these filters.</div></div>
{CALL_CARD}<script>{FILTER_JS}</script><script type="module">{CALL_JS}</script>""", "queue")


def _case_row(r, history, can_call):
    g, name, k = r["glid"], r["seller_name"] or f"Seller {r['glid']}", r["call_reason"]
    search = " ".join([g, name, r["category"], r["parent_category"] or "", k]).lower()
    demo = '<span class="badge demo">★ demo</span>' if g in DEMO_SELLERS else ""
    parent = r["parent_category"] if r["parent_category"] and r["parent_category"] != r["category"] else ""
    return f"""<tr class="row" data-href="/seller/{g}" data-q="{escape(search)}" data-r="{k}" data-s="{'done' if history else 'new'}" data-d="{'1' if demo else ''}">
<td><div class="who"><div class="av {k}">{escape(initials(name))}</div><div><b title="{escape(name)}">{escape(name)}</b><span class="muted small">GLID {g}</span> {demo}</div></div></td>
<td><span class="badge {k}">{TABS[k]}</span></td>
<td class="cat"><b>{escape(r['category'])}</b><div class="muted small">{escape(parent)}</div></td>
<td><span class="pct">{num(r['delivery_pct']):.0f}%</span> <span class="muted small">{r['leads_delivered']} of {r['lead_count']} leads</span>{bar(r['delivery_pct'])}</td>
<td><span class="pct">{num(r['delivery_28d_pct']):.0f}%</span> <span class="muted small">{r['leads_28d']} leads</span></td>
<td><div class="pitch">{_pitch(r)}</div></td><td>{status_badge(history)}</td>
<td><button class="btn sm call" data-glid="{g}" {'' if can_call else 'disabled title="Finish setup first"'}>{icon('phone')}Call</button></td></tr>"""


FILTER_JS = """
const state = {r: "", s: "", d: "", q: ""};
function apply() {
  let n = 0;
  document.querySelectorAll("#rows tr").forEach(tr => {
    const ok = (!state.r || tr.dataset.r === state.r) && (!state.s || tr.dataset.s === state.s) && (!state.d || tr.dataset.d === state.d) && tr.dataset.q.includes(state.q);
    tr.style.display = ok ? "" : "none"; n += ok;
  });
  document.getElementById("count").textContent = `${n} seller${n === 1 ? "" : "s"}`;
  document.getElementById("empty").style.display = n ? "none" : "block";
}
function seg(id, key, attr) {
  document.querySelectorAll(`#${id} button`).forEach(b => b.onclick = () => {
    document.querySelectorAll(`#${id} button`).forEach(x => x.classList.remove("on")); b.classList.add("on");
    state[key] = b.dataset[attr]; apply();
  });
}
seg("status", "s", "s"); seg("demo", "d", "d");
document.querySelectorAll(".kpi[data-f]").forEach(k => k.onclick = () => {
  document.querySelectorAll(".kpi").forEach(x => x.classList.remove("on")); k.classList.add("on"); state.r = k.dataset.f; apply();
});
document.getElementById("q").oninput = e => { state.q = e.target.value.toLowerCase().trim(); apply(); };
document.querySelectorAll("tr.row").forEach(tr => tr.onclick = e => { if (!e.target.closest("button,a")) location.href = tr.dataset.href; });
apply();
"""


@app.get("/seller/{glid}", response_class=HTMLResponse)
def seller(glid: str, request: Request):
    history = store.history(glid)
    row = seller_row(glid, history)
    if not row:
        return page("Not found", '<a class="crumb" href="/">← Call queue</a><div class="card empty">No call trigger for this seller.</div>')
    k, name = row["call_reason"], row["seller_name"] or f"Seller {glid}"
    missing = call_ready()
    timeline = "".join(
        f'<li><div class="ti">{EVENT_LOOK.get(e["type"], ("•", ""))[0]}</div><div><div class="t">{escape(EVENT_LOOK.get(e["type"], ("", e["type"]))[1])}'
        f'{" · " + escape(e["data"].get("channel", "")) if e["type"] == "outcome" and e["data"].get("channel") else ""}</div>'
        f'<div class="d">{escape(_event_text(e))}</div><div class="muted small">{when(e["at"])}</div></div></li>' for e in history)
    variables = "".join(f"<tr><td>{k_}</td><td>{escape(str(v))}</td></tr>" for k_, v in row.items() if k_ not in ("seller_md", "phone_number"))
    others = row["other_triggers"] or "None"
    facts = {
        "renew": [("Same plan", f"₹{int(row['plan_price']):,} for {row['lead_count']} leads"),
                  ("Smaller option", f"₹{int(row['smaller_plan_price']):,} for {row['smaller_plan_leads']} leads"),
                  ("If they say no", "Ask why, and what their plan with IndiaMART is now")],
        "upsell": [("Pitch", row["upsell_category"] or "No candidate above 200 enquiries/mo"),
                   ("Demand", f"~{row['upsell_organic_leads']} buyer enquiries/month" if row["upsell_organic_leads"]
                    else "From GMC listing and Google Ads impressions" if row["upsell_tier"] == "GMC" else "—"),
                   ("Why it fits", {"A": "Same parent category", "B": "Another category they deal in",
                                    "GMC": "They list products there but run no ads"}.get(row["upsell_tier"], "—")),
                   ("More new campaigns", row["other_campaigns"] or "None found in their GMC listing"),
                   ("Plans", row["plan_options"])],
        "improve": [("Products live", f"{row['product_count']} of 10"),
                    ("Suggest adding", row["suggested_products"] or "Campaign already full"),
                    ("Then", "Book a check-in call in about two weeks")],
    }[k]
    fact_html = "".join(f"<dt>{a}</dt><dd>{escape(str(b))}</dd>" for a, b in facts + [("Other triggers", others)])
    return page(name, f"""<a class="crumb" href="/">← Call queue</a>{flash(request)}
{setup_notice(missing)}
<div class="card"><div class="hero"><div class="av {k}">{escape(initials(name))}</div>
<div><h1>{escape(name)} <span class="badge {k}">{TABS[k]}</span>{' <span class="badge demo">★ demo</span>' if glid in DEMO_SELLERS else ''}</h1>
<div class="sub">GLID {glid} · Work order {row['work_order']} · {escape(row['category'])}{' · ' + escape(row['parent_category']) if row['parent_category'] and row['parent_category'] != row['category'] else ''}</div></div>
<div class="actions"><a class="btn ghost" href="/whatsapp/{glid}">{icon('chat')}WhatsApp</a>
<button class="btn call" data-glid="{glid}" {'' if not missing else 'disabled'}>{icon('phone')}Call with VANI</button></div></div>
<div class="stats"><div><div class="v">{num(row['delivery_pct']):.0f}%</div><div class="k">package delivered · {row['leads_delivered']}/{row['lead_count']}</div>{bar(row['delivery_pct'])}</div>
<div><div class="v">{num(row['delivery_28d_pct']):.0f}%</div><div class="k">last 28 days · {row['leads_28d']} leads</div>{bar(row['delivery_28d_pct'])}</div>
<div><div class="v">₹{int(row['plan_price']):,}</div><div class="k">current plan price</div></div>
<div><div class="v">{row['product_count']}</div><div class="k">products in campaign</div></div></div></div>
<div class="grid2" style="margin-top:18px"><div class="stack">
<div class="quote">{escape(row['opening_line'])}</div>
<div class="card"><h2>Call plan · {TABS[k]}</h2><dl class="kv">{fact_html}</dl></div>
<div class="card"><h2>History</h2>{f'<ul class="timeline">{timeline}</ul>' if history else '<div class="muted">No contact yet. The first call starts from the lead report.</div>'}</div>
{conversations(history)}
</div><div>
{gmc_card(glid)}
<details open><summary>seller.md · what VANI knows before it speaks</summary><pre>{escape(row['seller_md'])}</pre></details>
<details><summary>Agent variables ({len(row) - 2})</summary><table class="vars">{variables}</table></details></div></div>
{CALL_CARD}<script type="module">{CALL_JS}</script>""", "queue")


def gmc_card(glid):
    """Google Merchant Centre snapshot for the seller's call category, with a refresh button."""
    hits = [(r, w) for w in seller_work_orders(glid) if (r := reason_for(w))]
    wo = pick_primary(hits)[1]
    snap, (ak_ok, ak_msg) = gmc.load(glid), gmc.ak_status()
    button = (f'<form method="post" action="/seller/{glid}/gmc" style="display:inline" onsubmit="this.querySelector(\'button\').textContent=\'Fetching…\'">'
              f'<button class="btn ghost sm" {"" if ak_ok else "disabled"}>{"Refresh" if snap else "Fetch"} from GMC</button></form>')
    head = f'<div style="display:flex;justify-content:space-between;align-items:center;gap:8px"><h2 style="margin:0">Google Merchant Centre</h2>{button}</div>'
    if not ak_ok:
        note = f'<p class="muted small">{escape(ak_msg)}. Paste a fresh AK token on <a href="/setup">Setup</a> to fetch.</p>'
    else:
        note = ""
    if not snap:
        if ak_ok:  # load it in the background so the page itself opens instantly
            return (f'<div class="card" style="margin-bottom:12px">{head}<p class="muted small" id="gmc-auto">Fetching GMC data…</p></div>'
                    f'<script>fetch("/seller/{glid}/gmc.json", {{method: "POST"}}).then(r => r.json()).then(j => j.ok ? location.reload() : '
                    f'(document.getElementById("gmc-auto").textContent = "GMC fetch failed: " + j.error))</script>')
        return f'<div class="card" style="margin-bottom:12px">{head}{note}<p class="muted small">No GMC data yet.</p></div>'
    c = gmc_campaign(wo)
    age = f"fetched {when(snap['fetched_at'])}" + (f" · {escape(snap['status_error'])}" if snap.get("status_error") else "")
    if not c:
        body = f'<p>{snap["product_count"]} products, none in <b>{escape(wo["category"])}</b>.</p>'
    else:
        stat = lambda r: {"Live": "good", "Pending": "neutral", "Unavailable": "bad"}.get(r["status"], "new")
        rows = "".join(
            f'<tr><td>{escape(r["title"])}<div class="muted small">{escape(", ".join(gmc.issues(r)) or "feed looks complete")}</div></td>'
            f'<td>{"₹" + format(int(r["price"]), ",") if r["price"] else "—"}</td>'
            f'<td><span class="badge {stat(r)}">{r["status"] if r["status"] != "Unavailable" else "not pushed"}</span></td></tr>'
            for r in sorted(c["rows"], key=lambda r: ({"Live": 0, "Pending": 1}.get(r["status"], 2), -gmc.quality(r)))[:25])
        body = (f'<div class="stats" style="grid-template-columns:repeat(3,1fr);margin-top:12px"><div><div class="v">{c["live"]}</div><div class="k">live in {escape(wo["category"])}</div></div>'
                f'<div><div class="v">{c["pending"]}</div><div class="k">pending</div></div><div><div class="v">{len(c["candidates"])}</div><div class="k">can be added</div></div></div>'
                + (f'<div class="notice" style="margin:14px 0 0">Feed problems: {escape(gmc.issues_line(c))}</div>' if gmc.issues_line(c) else "")
                + f'<table class="vars" style="margin-top:12px">{rows}</table>')
    return f'<div class="card" style="margin-bottom:12px">{head}<p class="muted small" style="margin:4px 0 0">{age}</p>{note}{body}</div>'


@app.post("/seller/{glid}/gmc.json")
def gmc_refresh_json(glid: str):
    try:
        return {"ok": True, "products": gmc.fetch(glid)["product_count"]}
    except Exception as e:
        return {"ok": False, "error": str(e)[:250]}


@app.post("/seller/{glid}/gmc")
def gmc_refresh(glid: str):
    try:
        msg = f"Fetched {gmc.fetch(glid)['product_count']} products from GMC"
        return RedirectResponse(f"/seller/{glid}?msg={quote(msg)}", status_code=303)
    except Exception as e:
        return RedirectResponse(f"/seller/{glid}?err={quote('GMC fetch failed: ' + str(e)[:250])}", status_code=303)


@app.post("/seller/{glid}/call")
async def call_now(glid: str, request: Request):
    """Phone call through Sarvam's outbound API (kept for later; the UI uses the in-browser call)."""
    form = await request.form()
    phone = str(form.get("phone", "")).strip()
    try:
        attempt = sarvam.place_call(glid, phone).get("attempt_id")
        return RedirectResponse(f"/seller/{glid}?msg={quote(f'Calling {phone} (attempt {attempt})')}", status_code=303)
    except Exception as e:  # show the Sarvam error on the page instead of a 500
        return RedirectResponse(f"/seller/{glid}?err={quote(str(e)[:300])}", status_code=303)


@app.get("/activity", response_class=HTMLResponse)
def activity(request: Request):
    events = store.recent(100)
    names = {r["glid"]: r["seller_name"] for r in build_rows("", store.history_by_seller())}
    items = "".join(
        f'<li><div class="ti">{EVENT_LOOK.get(e["type"], ("•", ""))[0]}</div><div><div class="t">{escape(EVENT_LOOK.get(e["type"], ("", e["type"]))[1])} · '
        f'<a href="/seller/{e["glid"]}">{escape(names.get(e["glid"]) or e["glid"])}</a></div><div class="d">{escape(_event_text(e))}</div>'
        f'<div class="muted small">{when(e["at"])}</div></div></li>' for e in events)
    return page("Activity", f"""<div class="top"><div><h1>Activity</h1><div class="sub">Every call outcome, WhatsApp message, link, quote and callback, newest first.</div></div></div>
<div class="card">{f'<ul class="timeline">{items}</ul>' if items else '<div class="empty">Nothing yet. Start a call from the queue.</div>'}</div>""", "activity")


@app.get("/setup", response_class=HTMLResponse)
def setup(request: Request):
    e = sarvam.env
    keys = [("SARVAM_API_KEY", "Chat model: WhatsApp bot and outcome extraction", bool(e("SARVAM_API_KEY"))),
            ("SARVAM_AGENT_API_KEY", "Voice agent key (falls back to SARVAM_API_KEY)", bool(sarvam.agent_key())),
            ("SARVAM_ORG_ID", "Organisation", bool(e("SARVAM_ORG_ID"))), ("SARVAM_WORKSPACE_ID", "Workspace", bool(e("SARVAM_WORKSPACE_ID"))),
            ("SARVAM_APP_ID", "Agent (app) ID", bool(e("SARVAM_APP_ID"))), ("SARVAM_APP_VERSION", "Committed version", bool(e("SARVAM_APP_VERSION"))),
            ("TOOLS_TOKEN", "Auth for /tools and /webhooks", bool(e("TOOLS_TOKEN"))), ("PUBLIC_URL", "Only for hosted tools and webhooks", bool(e("PUBLIC_URL")))]
    checks = "".join(f'<div class="check"><span class="badge {"good" if ok else "bad"}">{"set" if ok else "missing"}</span><code>{k}</code>'
                     f'<span class="muted">{d}</span></div>' for k, d, ok in keys)
    live, ak = live_status(fresh=True), gmc.ak_status()
    return page("Setup", f"""<div class="top"><div><h1>Setup</h1><div class="sub">What the dashboard needs from <code>.env</code>. Values are never shown.</div></div></div>
<div class="grid2"><div class="card"><h2>Settings</h2>{checks}</div>
<div class="card"><h2>Live check · Sarvam voice agent</h2>
<div class="notice {'ok' if live[0] else 'err'}" style="margin:0 0 12px">{'✅' if live[0] else '❌'} {escape(live[1])}</div>
<p class="muted small">Asks Sarvam for a session URL for app {escape(e('SARVAM_APP_ID') or '—')}, version {escape(e('SARVAM_APP_VERSION') or 'latest')}. This is the same request 📞 Call makes. Nothing is dialled.</p>
<a class="btn ghost sm" href="/setup">Run again</a></div>
<div class="card"><h2>Google Merchant Centre · AK token</h2>
<div class="notice {'ok' if ak[0] else 'err'}" style="margin:0 0 12px">{'✅' if ak[0] else '❌'} {escape(ak[1])}</div>
<p class="muted small">Improve calls read the seller's real products from the same IndiaMART services as ads-next's GMC Feed page.
They need your AK token, which lasts about a day. Get it by signing in to ads-next, then DevTools → Application → Cookies → <code>AK_Key</code>.</p>
<form method="post" action="/setup/ak" style="display:flex;gap:8px"><input name="token" type="password" placeholder="Paste AK_Key value" required
style="flex:1;border:1px solid var(--line);border-radius:10px;padding:8px 12px;font:inherit"><button class="btn sm">Save</button></form></div></div>""", "settings")


@app.post("/setup/ak")
async def setup_ak(request: Request):
    """Save a fresh AK token to .env (and this process) without restarting."""
    token = str((await request.form()).get("token", "")).strip()
    if token.count(".") == 2:
        set_key(ENV_PATH, "IM_AK_TOKEN", token, quote_mode="never")
        os.environ["IM_AK_TOKEN"] = token
    return RedirectResponse("/setup", status_code=303)


_live = {"at": 0.0, "result": (False, "")}


def live_status(fresh=False):
    """The live check, cached for 5 minutes so every page can show it in the sidebar."""
    if call_ready():
        return False, f"Missing {', '.join(call_ready())}."
    if fresh or time.time() - _live["at"] > 300:
        _live.update(at=time.time(), result=_live_check())
    return _live["result"]


def _live_check():
    e = sarvam.env
    url = (f"{APP_RUNTIME}orgs/{e('SARVAM_ORG_ID')}/workspaces/{e('SARVAM_WORKSPACE_ID')}/apps/{e('SARVAM_APP_ID')}/url"
           + (f"?version={e('SARVAM_APP_VERSION')}" if e("SARVAM_APP_VERSION") else ""))
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"X-API-Key": sarvam.agent_key()}), timeout=15):
            return True, "Connected. Sarvam issued a session URL, so 📞 Call will work."
    except urllib.error.HTTPError as err:
        body = err.read().decode(errors="replace")
        try:
            detail = json.loads(body)["error"]["data"]["details"]
        except (ValueError, KeyError, TypeError):
            detail = body[:200]
        hint = (" The sk_ key works for chat but not voice agents; create a voice-agents key on indus.sarvam.ai and set SARVAM_AGENT_API_KEY."
                if err.code == 401 else "")
        return False, f"Sarvam said {err.code}: {str(detail).rstrip('.')}.{hint}"
    except Exception as err:  # network errors
        return False, f"Could not reach Sarvam: {err}"


@app.get("/whatsapp/{glid}", response_class=HTMLResponse)
def whatsapp(glid: str, request: Request):
    row = seller_row(glid, store.history(glid))
    name = (row or {}).get("seller_name") or f"Seller {glid}"
    msgs = "".join(f"<div class='msg {'in' if m['type'] == 'whatsapp_in' else 'out'}'>{escape(m['data']['text'])}"
                   f"<small>{m['at'][11:16]}{'' if m['type'] == 'whatsapp_in' else (' · sent during call' if m['data'].get('channel') == 'system' else ' · VANI')}</small></div>"
                   for m in sarvam.whatsapp_thread(glid)) or "<div class='msg out'>Type a message as the seller to start the chat.</div>"
    return page(f"WhatsApp · {name}", f"""<a class="crumb" href="/seller/{glid}">← {escape(name)}</a>{flash(request)}
<div class="top"><div><h1>WhatsApp follow-up</h1><div class="sub">You are the seller. VANI replies with the same context, history and tools as the voice call.</div></div></div>
<div class="phone"><div class="phone-top"><div class="av">{escape(initials(name))}</div><div><b>{escape(name)}</b><div class="small" style="opacity:.75">chatting with IndiaMART · VANI</div></div></div>
<div class="wa" id="wa">{msgs}</div>
<form class="wa-form" method="post" action="/whatsapp/{glid}" onsubmit="this.querySelector('button').textContent='…'"><input name="text" placeholder="Message" required autofocus autocomplete="off"><button>➤</button></form></div>
<script>const w=document.getElementById("wa");w.scrollTop=w.scrollHeight;</script>""", "queue")


@app.post("/whatsapp/{glid}")
async def whatsapp_send(glid: str, request: Request):
    text = str((await request.form()).get("text", "")).strip()
    try:
        if text:
            sarvam.whatsapp_reply(glid, text)
        return RedirectResponse(f"/whatsapp/{glid}", status_code=303)
    except Exception as e:
        return RedirectResponse(f"/whatsapp/{glid}?err={quote(str(e)[:300])}", status_code=303)


@app.get("/cohort.csv")
def cohort(phone: str = "", reason: str = ""):
    rows = [r for r in build_rows(phone, store.history_by_seller()) if not reason or r["call_reason"] == reason]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="vani-cohort{"-" + reason if reason else ""}.csv"'})


# --- In-browser call: talk to VANI as any seller ---------------------------------------------
APP_RUNTIME = "https://apps.sarvam.ai/api/app-runtime/"
BROWSER_ENV = ("SARVAM_AGENT_API_KEY", "SARVAM_ORG_ID", "SARVAM_WORKSPACE_ID", "SARVAM_APP_ID")


@app.get("/sarvam-proxy/{path:path}")
def sarvam_proxy(path: str, request: Request):
    """The browser SDK asks here for a signed WebSocket URL; we add the API key server-side.
    Only our own agent's signed-URL endpoint is allowed, so this isn't an open proxy."""
    e = sarvam.env
    allowed = f"orgs/{e('SARVAM_ORG_ID')}/workspaces/{e('SARVAM_WORKSPACE_ID')}/apps/{e('SARVAM_APP_ID')}/url"
    if path != allowed:
        return JSONResponse({"error": "not allowed"}, status_code=404)
    url = APP_RUNTIME + path + (f"?{request.url.query}" if request.url.query else "")
    req = urllib.request.Request(url, headers={"X-API-Key": sarvam.agent_key()})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return Response(resp.read(), status_code=resp.status, media_type="application/json")
    except urllib.error.HTTPError as err:
        return Response(err.read(), status_code=err.code, media_type="application/json")


CALL_CARD = """<aside id="callcard"><div class="cc-top"><div class="pulse" id="cc-av">V</div>
<div><b id="cc-name">Calling…</b><small id="cc-sub"></small></div><div class="cc-time" id="cc-time">00:00</div></div>
<div class="cc-state" id="cc-state">Preparing…</div><div class="cc-chat" id="cc-chat"></div>
<div class="cc-result" id="cc-result"></div>
<div class="cc-foot"><button class="btn red" id="cc-end">End call</button></div></aside>"""

# Browser call with the Sarvam web SDK. The SDK fetches a signed URL via /sarvam-proxy/, which adds the key server-side.
CALL_JS = """
import { ConversationAgent, BrowserAudioInterface, InteractionType } from "https://esm.sh/sarvam-conv-ai-sdk@0.0.42/browser";
const $ = (id) => document.getElementById(id);
let agent = null, lines = [], glid = null, t0 = 0, timer = null;
const esc = (s) => String(s).replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
function setState(s) { $("cc-state").innerHTML = s; }
function show(role, text) {
  lines.push(`${role === "user" ? "Seller" : "VANI"}: ${text}`);
  const d = document.createElement("div"); d.className = "msg " + (role === "user" ? "in" : "out");
  d.innerHTML = `${esc(text)}<small>${role === "user" ? "You (seller)" : "VANI"}</small>`;
  $("cc-chat").appendChild(d); $("cc-chat").scrollTop = $("cc-chat").scrollHeight;
}
function logGmc(g, s) {  // GMC report for this call, in DevTools → Console
  const m = s.gmc || {};
  console.groupCollapsed(`%c[VANI] GMC for ${s.vars.seller_name || g} · ${m.source}`, "color:#2f3fbf;font-weight:bold");
  console.log(m);
  if (m.api_log && m.api_log.length) { console.log(`API requests (${m.fetch_ms ?? "?"}ms total):`); console.table(m.api_log); }
  if (m.error) console.error("GMC fetch failed:", m.error);
  if (m.category) { console.log(`${m.category.name}: ${m.category.listed} listed, ${m.category.in_campaign} in campaign, pitch = ${m.category.pitch}`);
                    if (m.category.products_to_add.length) console.table(m.category.products_to_add); }
  console.log("Variables sent to the agent:", s.vars);
  console.groupEnd();
}
function tick() { const s = Math.floor((Date.now() - t0) / 1000); $("cc-time").textContent = `${String(s / 60 | 0).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`; }
function fail(msg) {
  if (/401|API key/i.test(msg)) msg = "Sarvam rejected the API key. Voice agents need their own key: see Setup.";
  setState(`<span style="color:#b42318">⚠️ ${esc(msg)}</span>`);
}
async function finish() {
  const a = agent; agent = null; clearInterval(timer); $("cc-av").classList.remove("live");
  $("cc-end").textContent = "Close"; $("cc-end").className = "btn ghost";
  if (a) await a.stop().catch(() => {});
  if (!lines.length) return;
  setState("Call ended · reading the transcript for the outcome…");
  const r = await fetch(`/test/${glid}/end`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({transcript: lines.join("\\n")})});
  const j = await r.json().catch(() => ({}));
  lines = [];
  if (!j.logged) return setState("Call ended.");
  const o = j.outcome || {};
  setState("Call ended · outcome saved to the seller's history");
  $("cc-result").style.display = "block";
  $("cc-result").innerHTML = `<b>${esc((o.call_outcome || "other").replace(/_/g, " "))}</b>` +
    (o.objection ? `<div>Objection: ${esc(o.objection)}</div>` : "") + (o.next_step ? `<div>Next: ${esc(o.next_step)}</div>` : "") +
    `<div style="margin-top:6px"><a href="/seller/${glid}">Open seller</a> · <a href="">Refresh queue</a></div>`;
}
$("cc-end").onclick = () => agent ? finish() : $("callcard").classList.remove("on");
async function startCall(g) {
  if (agent) return alert("A call is already running. End it first.");
  glid = g; lines = [];
  $("callcard").classList.add("on"); $("cc-chat").innerHTML = ""; $("cc-result").style.display = "none";
  $("cc-end").textContent = "End call"; $("cc-end").className = "btn red"; $("cc-time").textContent = "00:00";
  setState("Loading seller context…");
  try {
    setState("Fetching GMC data and seller context…");
    const s = await (await fetch(`/agent-session/${g}`)).json();
    if (s.error) throw new Error(s.error);
    logGmc(g, s);
    $("cc-name").textContent = s.vars.seller_name || `Seller ${g}`;
    $("cc-sub").textContent = `${s.vars.call_reason} · ${s.vars.category}`;
    agent = new ConversationAgent({
      apiKey: "", baseUrl: location.origin + "/sarvam-proxy/",
      config: { ...s.config, user_identifier: "test-" + g, user_identifier_type: "custom",
        interaction_type: InteractionType.CALL, input_sample_rate: 16000, output_sample_rate: 22050,
        agent_variables: s.vars, initial_bot_message: s.vars.opening_line },
      audioInterface: new BrowserAudioInterface(16000),
      stateCallback: (st) => { if (agent) setState(`● ${esc(st)}`); },
      transcriptCallback: async (m) => show(m.role, m.content),
      endCallback: async () => { if (agent) await finish(); },
    });
    setState("Connecting… allow the microphone when asked");
    await agent.start();
    if (!(await agent.waitForConnect(15))) throw new Error("Timed out connecting to the agent");
    t0 = Date.now(); timer = setInterval(tick, 1000); $("cc-av").classList.add("live");
    setState("● Live · speak as the seller");
  } catch (e) { fail(String(e.message || e)); await finish(); }
}
document.querySelectorAll("button.call").forEach(b => b.addEventListener("click", (e) => { e.stopPropagation(); startCall(b.dataset.glid); }));
"""


def _agent_config():
    e = sarvam.env
    v = e("SARVAM_APP_VERSION")
    return {"org_id": e("SARVAM_ORG_ID"), "workspace_id": e("SARVAM_WORKSPACE_ID"), "app_id": e("SARVAM_APP_ID"),
            **({"version": int(v)} if v.isdigit() else {})}


@app.get("/agent-session/{glid}")
def agent_session(glid: str):
    """Everything the browser call needs for one seller: agent IDs and that seller's variables.
    Every call fetches the seller's GMC data fresh (falling back to the cached copy) so VANI talks about real products,
    and returns a `gmc` report (API requests, timings, pitch) that the browser prints to its console."""
    row = seller_row(glid, store.history(glid))
    if not row:
        return JSONResponse({"error": "no call trigger for this seller"}, status_code=404)
    debug = {"source": "none", "api_log": []}
    snap = gmc.load(glid)
    ak_ok, ak_msg = gmc.ak_status()
    if not ak_ok:
        debug["source"] = f"{'stale cache' if snap else 'mock data'}: {ak_msg}"
    else:
        try:
            snap = gmc.fetch(glid)
            debug.update(source="GMC API (fresh)", api_log=snap["api_log"], fetch_ms=snap["fetch_ms"])
            row = seller_row(glid, store.history(glid))
        except Exception as e:  # keep the call going on the cached or mock data
            debug.update(source=f"{'stale cache' if snap else 'mock data'}: fetch failed", error=str(e), api_log=list(gmc.calls()))
    wo = pick_primary([(r, w) for w in seller_work_orders(glid) if (r := reason_for(w))])[1]
    c = gmc_campaign(wo) if snap else None
    if snap:
        debug.update(fetched_at=snap["fetched_at"], products=snap["product_count"],
                     live=sum(r["status"] == "Live" for r in snap["rows"]), status_error=snap.get("status_error") or None)
    if c:
        debug["category"] = {"name": wo["category"], "listed": c["in_category"], "in_campaign": c["live"], "pending": c["pending"],
                             "pitch": c["mode"], "products_to_add": [{"title": r["title"], "impressions": r["impressions"],
                                                                      "price": r["price"]} for r in c["candidates"]]}
    gmc.log(f"call start {glid} ({row['call_reason']}): data from {debug['source']}"
            + (f"; {wo['category']}: {c['in_category']} listed, {c['live']} in campaign, pitch={c['mode']}" if c else ""))
    return {"config": _agent_config(), "vars": {k: str(v) for k, v in row.items() if k != "phone_number"}, "gmc": debug}


@app.post("/test/{glid}/end")
async def test_end(glid: str, request: Request):
    """Called when a browser call ends: extract the outcome from the transcript and log it."""
    transcript = str((await request.json()).get("transcript", "")).strip()
    if not transcript or not seller_work_orders(glid):
        return {"logged": False}
    try:
        outcome = sarvam.extract_outcome(transcript)
    except Exception:  # still keep the transcript if the model is unavailable
        outcome = {}
    tools.log_outcome(glid, channel="browser call", transcript=transcript, summary=outcome.get("summary", ""),
                      **{k: outcome.get(k) for k in tools.OUTCOME_FIELDS})
    return {"logged": True, "outcome": outcome}


@app.get("/test")
def test_agent(glid: str = DEMO_SELLERS[0]):
    """Old test page: the call now lives on the queue and seller pages."""
    return RedirectResponse(f"/seller/{glid}", status_code=303)

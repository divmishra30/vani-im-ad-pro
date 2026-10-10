# VANI for IM Ad Pro sellers

An outbound voice agent on Sarvam (indus.sarvam.ai) that already knows the seller before it speaks. It calls IndiaMART Ads sellers about one of three things, decided from the daily lead report:

| Call | Trigger (per work order) | Goal |
|---|---|---|
| 1 · Renew | Act. Del. Bucket **>80%** | Renew the package; if not, ask why and what their plan with us is |
| 2 · Upsell | Act. Del. Bucket **50–80%** | Sell Ads in another MCAT under the same PMCAT (tier A), else under the PMCAT of another of the seller's categories (tier B); >200 buyer enquiries/month |
| 3 · Improve | **28D Delivery% <50%** | Find out why it's under-delivering; add proven products if the campaign has fewer than 10 |

Each seller gets one call, about their most urgent work order (renew, then upsell, then improve).

## Architecture

```
lead reports ──> vani/core.py ──> seller context (seller.md, opening line, variables)
                    │                     │
                    │                     ├── campaign CSV (build_cohort.py)  ──> Sarvam Campaigns
                    │                     └── server.py on-start hook / tools  <── Sarvam voice agent
                    │
vani/store.py (SQLite) <── call outcomes (webhook / on-end hook), WhatsApp, callbacks, product adds
                    └──> History section of seller.md, so the next call and chat resume from here
```

- **Memory across calls:** every call's full transcript is stored with its outcome and a short summary, from both browser calls and Sarvam's phone webhook. The next call's `seller_md` gets a "Last conversation" section: the summary plus the end of the transcript, up to 1,500 characters. The opening line also picks up from it ("9 October ko humne… baat ki thi"). The seller page shows every transcript under **Conversations**.
- **Real GMC data for improve calls** (`vani/gmc.py`, ported from ads-next's GMC Feed): the seller's product listing joined with Merchant Centre status (Live / Pending / not pushed). Improve calls fetch it when they start (cached in `data/gmc/`, refreshed after 12 hours), and it replaces the mock with:
  - the live product count in the ad category
  - the seller's own products to add, best feed quality first
  - feed problems on live products (no price, no photo, short description, few specs), as the `gmc_issues` variable

  What VANI pitches depends on how many products the seller lists in the category:
  - **Fewer than 10:** add all the other products they have there.
  - **10 or more:** add the top 3 by Google Ads impressions from `data/Product data.csv` (`product_id` = GMC display ID). Without impressions, the best-quality listings are used.
  - **Nothing to add:** ask them to list more products in the category.

  It needs an AK token (`IM_AK_TOKEN`, valid about a day; paste it on **Setup**) and the office network or VPN. It is read-only: nothing is pushed to Merchant Centre.
- **Sarvam** does the voice: speech-to-text, LLM, text-to-speech and telephony.
- **`server.py`** (FastAPI) does everything else:
  - **Dashboard** `/`: the call queue. Click a seller to see their `seller.md`, history and agent variables.
  - **Call now**: dials a seller through Sarvam's outbound API, preloaded with their context.
  - **WhatsApp follow-up** `/whatsapp/<glid>`: a chat on `sarvam-105b` with the same context and tools, continuing from the call (links and quotes sent during the call appear in it).
  - **Tools** `/tools/<name>` and the **webhook** `/webhooks/sarvam` for the voice agent.
  - **Cohort CSV** `/cohort.csv?phone=…` for Sarvam Campaigns.

## Files

| Path | What |
|---|---|
| `vani/core.py` | Data loading, trigger rules, upsell picker, product suggestions, seller.md |
| `vani/tools.py` | Tools shared by the voice agent and the WhatsApp bot |
| `vani/store.py` | Call history (SQLite, `data/vani.db`) |
| `vani/sarvam.py` | Outbound calls and the WhatsApp bot |
| `server.py` | The web app |
| `build_cohort.py` | Offline campaign CSVs into `sarvam/` (works without the server) |
| `data/` | Lead reports and the MCAT → PMCAT mapping |
| `sarvam/1-instructions.md` … `4-tools-and-hooks.md` | What to paste into the Sarvam agent |

## Run locally

```bash
pip install -r requirements.txt
uvicorn server:app --reload --port 8000     # http://localhost:8000, any username + DASHBOARD_PASSWORD
```

`.env` keys:

| Key | Needed for |
|---|---|
| `SARVAM_API_KEY` | WhatsApp bot and outcome extraction (`sarvam-105b` chat; the `sk_…` key) |
| `SARVAM_AGENT_API_KEY` | Call and Talk: the voice-agents key from indus.sarvam.ai → Settings → API keys |
| `TOOLS_TOKEN` | Bearer token Sarvam sends to `/tools/*` and `/webhooks/*` |
| `DASHBOARD_PASSWORD` | Basic auth on the dashboard (it shows seller data) |
| `PUBLIC_URL` | The deployed URL, so outbound calls report back to `/webhooks/sarvam` |
| `SARVAM_ORG_ID`, `SARVAM_WORKSPACE_ID`, `SARVAM_APP_ID`, `SARVAM_APP_VERSION`, `SARVAM_CONNECTION_ID`, `SARVAM_AGENT_PHONE` | Call now (from the Sarvam dashboard once the agent and a phone number exist) |

## Deploy (GitHub + Render)

1. Push this folder to a **private** GitHub repo. `.env` and `data/vani.db` are git-ignored.
2. On render.com, sign in with GitHub, then **New + → Blueprint** and pick the repo. It reads `render.yaml`.
3. Fill in the env vars in Render (same keys as `.env`; set `PUBLIC_URL` to the Render URL).
4. Use the Render URL as `BASE` in `sarvam/4-tools-and-hooks.md`.

The free tier sleeps after 15 minutes idle (the first request then takes about 30–50s) and its disk is wiped on redeploy, which clears the call history. Open the dashboard before a demo to wake it.

## Set up the agent on indus.sarvam.ai

Follow `sarvam/1-instructions.md`, `2-variables.md`, `3-knowledge-base.md` and `4-tools-and-hooks.md`, then commit a version, add a phone number, and either use **Call now** on the dashboard or a Campaign with `sarvam/cohort-demo.csv`.

Demo sellers: renew **154979145** (Miracle Tools), upsell **118932009** (Sovisy India → RCC Water Tank), improve **132281146** (Chirab Technologies).

## Still mock / not in the data

- **Plan prices** by tier, and the smaller-plan option (`TIER_PRICE` in `vani/core.py`).
- **Campaign product counts and peer top products** (generated per work order).
- **Payment links, WhatsApp delivery and campaign edits** are recorded and shown in the WhatsApp page, but not sent to real IndiaMART systems.
- **PMCAT → MCAT list** only covers MCATs in the report, so 1 of 17 upsell sellers has a pitch today. Drop a fuller export with a demand column into `data/mcat-pmcat-mapping.csv`.
- **No seller phone numbers**: calls go to the number you enter.

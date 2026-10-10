# VANI · Variables tab

Create these on **Variables**. Names must match the column names in `cohort-*.csv` exactly, so the campaign maps them automatically.

## Input variables (one CSV column each)

Defaults = the **renew demo seller** (Miracle Tools), so **Test agent** works without a campaign. To test another seller, paste its values from `cohort-demo.csv`, or its `sellers/<glid>.md` file into `seller_md`.

| Variable | Default (renew demo) |
|---|---|
| glid | 154979145 |
| seller_name | Miracle Tools And Tackle LLP |
| call_reason | renew |
| work_order | 12813353 |
| category | Tool Kits |
| parent_category | Tool Kits |
| lead_count | 100 |
| leads_delivered | 96 |
| delivery_pct | 96 |
| leads_28d | 0 |
| delivery_28d_pct | 0 |
| plan_price | 12000 |
| smaller_plan_leads | 60 |
| smaller_plan_price | 7400 |
| product_count | 10 |
| suggested_products | (blank) |
| suggested_product_count | 0 |
| upsell_category | (blank) |
| upsell_organic_leads | 0 |
| upsell_tier | (blank) |
| other_triggers | upsell: Tool Trolley |
| other_campaigns | (blank; from GMC, e.g. "Vessel Sealing System (41 products listed); Diathermy Machine (11 products listed)") |
| plan_options | Standard 12,000 rupees (current), Premium 18,000 rupees, Platinum 30,000 rupees |
| gmc_issues | (blank; filled from real GMC data, e.g. "3 of 6 live products have no price") |
| opening_line | Namaste! Main IndiaMART se VANI bol rahi hoon. Kya meri baat Miracle Tools And Tackle LLP se ho rahi hai? Aapke Tool Kits ads ki 96 percent delivery ho chuki hai, isliye renewal ke baare mein baat karni thi. Do minute baat kar sakte hain? |
| seller_md | contents of `sellers/154979145.md` |

Other demo sellers (rows in `cohort-demo.csv`):
- upsell: **118932009**, Sovisy India Private Limited. SMC Panel Tanks, pitch RCC Water Tank (~242 enquiries/month, same parent: Industrial Water Tanks).
- improve: **132281146**, Chirab Technologies. Transformer Tester, 1 lead in 28 days, 6 products, 4 suggested.

## Output variables (filled by the LLM after each call)

These are the write-back: they appear per call in **Monitor → Agent Analytics / Call Logs**.

| Variable | Type | Extraction prompt |
|---|---|---|
| call_outcome | Enum: `renewal_agreed`, `renewal_declined`, `upsell_interested`, `upsell_declined`, `products_approved`, `improve_declined`, `callback_requested`, `wrong_person_or_busy`, `do_not_call`, `other` | What was the final result of this call? |
| renewal_plan | Enum: `same`, `smaller`, `none` | If the seller agreed to renew, which plan did they choose? |
| objection | String | The seller's main objection or reason for saying no, in one short line. Empty if none. |
| seller_plan | String | If the seller declined to renew: what is their plan with IndiaMART now (pause, other category, budget later, unhappy with leads...)? One line. |
| callback_time | String | If a callback or check-in was agreed, when (as the seller said it). Empty if none. |
| whatsapp_to_send | Enum: `renewal_link`, `upsell_quote`, `product_list`, `none` | What did VANI promise to send on WhatsApp? |
| next_step | String | The agreed next step, in one line. |

**Call goal** (Settings): `call_outcome` is `renewal_agreed`, `upsell_interested` or `products_approved`.

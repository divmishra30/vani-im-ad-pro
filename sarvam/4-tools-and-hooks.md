# VANI · Tools and hooks (with our backend)

These connect the Sarvam agent to `server.py`. `BASE` = the backend's public URL, e.g. `https://vani-im-ad-pro.onrender.com`.

Settings shared by every API tool:
- **Method:** POST · **Header:** `Content-Type: application/json`
- **Auth:** Bearer, with the `TOOLS_TOKEN` value from `.env` (store it as a workspace secret)
- **Max wait:** 8s (the free Render tier can be slow on the first request) · **If it fails:** "Maaf kijiye, system se details nahi mil pa rahi. Main aapko thodi der mein call karwa deti hoon."
- **Response template:** `@summary` (every tool returns a one-line `summary`)
- In bodies, `@x` = agent variable `x` inserted as a chip. `@call_transcript` and `@interaction_id` are Sarvam's call-context variables.

## On-start hook · get_seller_context

Loads the **latest** context, including past calls and WhatsApp, before the greeting. This overrides the campaign CSV values with fresher ones.

- URL `BASE/tools/get_seller_context` · Body `{ "glid": "@glid" }`
- **Save reply into variables:** each key into the variable of the same name:
  `seller_name, call_reason, work_order, category, parent_category, lead_count, leads_delivered, delivery_pct, leads_28d, delivery_28d_pct, plan_price, smaller_plan_leads, smaller_plan_price, product_count, suggested_products, suggested_product_count, upsell_category, upsell_organic_leads, upsell_tier, other_triggers, opening_line, seller_md`

Add an input variable **work_order** (default `12813353`), which the tools use.

## On-end hook · log_outcome

Writes the result back so the next call and the WhatsApp bot start from it.

- URL `BASE/tools/log_outcome`
- Body:
```json
{
  "glid": "@glid",
  "call_outcome": "@call_outcome",
  "renewal_plan": "@renewal_plan",
  "objection": "@objection",
  "seller_plan": "@seller_plan",
  "callback_time": "@callback_time",
  "whatsapp_to_send": "@whatsapp_to_send",
  "next_step": "@next_step",
  "interaction_id": "@interaction_id",
  "transcript": "@call_transcript"
}
```

Calls started with **Call now** on the dashboard also send Sarvam's end-of-call webhook to `BASE/webhooks/sarvam`, which records the same thing. For campaigns, put `BASE/webhooks/sarvam?token=<TOOLS_TOKEN>` in **Advanced → Webhook URL**.

## Mid-call tools

| Name | Description (the agent reads this to decide when to call it) | Body |
|---|---|---|
| get_package_status | Current package delivery and renewal prices. Call before quoting any price. | `{ "glid": "@glid" }` |
| create_renewal_link | Create the renewal payment link and send it on WhatsApp. Only after the seller agrees to renew. | `{ "glid": "@glid", "plan": "@renewal_plan" }` |
| get_upsell_candidates | The one best new category to offer, with its monthly buyer demand. Call before pitching. | `{ "glid": "@glid" }` |
| send_quote | Send a price quote for the new category on WhatsApp, when the seller is interested. | `{ "glid": "@glid", "category": "@upsell_category" }` |
| get_peer_top_products | Best products to add to an under-delivering campaign. | `{ "glid": "@glid" }` |
| add_products_to_campaign | Add the suggested products. Only after a clear verbal yes. Returns the new product count. | `{ "glid": "@glid" }` |
| schedule_callback | Book a follow-up call at the time the seller asked for. | `{ "glid": "@glid", "time": "@callback_time", "reason": "@call_reason", "transcript": "@call_transcript" }` |

`create_renewal_link` treats an empty or unknown `plan` as the same plan.

## Test without Sarvam

```bash
curl -X POST BASE/tools/get_package_status -H "Authorization: Bearer $TOOLS_TOKEN" -H "Content-Type: application/json" -d '{"glid":"154979145"}'
```

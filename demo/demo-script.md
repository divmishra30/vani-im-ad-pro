# VANI · Demo video script

**Length:** about 5 minutes · **Format:** dashboard screens + three voiced calls with captions
**Voices:** NARRATOR (English, neutral) · VANI (female, Hinglish, Sarvam voice) · SELLER (male, Hinglish, a different voice for each seller)

Every number below comes from the real lead report (`sarvam/cohort-demo.csv`). Plan prices are still mock (`TIER_PRICE` in `vani/core.py`).

| # | Scene | Screen | Time |
|---|---|---|---|
| 1 | The problem | Title card | 0:00–0:25 |
| 2 | VANI knows the seller first | Dashboard `/` → seller page | 0:25–1:00 |
| 3 | Call 1 · Renew | `/seller/154979145` + call captions | 1:00–2:05 |
| 4 | Call 2 · Upsell | `/seller/118932009` + call captions | 2:05–3:10 |
| 5 | Call 3 · Improve | `/seller/132281146` + call captions | 3:10–4:15 |
| 6 | After the call | Conversations, `/whatsapp/118932009`, next opening line | 4:15–4:45 |
| 7 | Close | Title card | 4:45–5:00 |

---

## Scene 1 · The problem  (0:00–0:25)

**SCREEN:** Black title card: "VANI · the voice agent for IM Ad Pro sellers". Then three stat lines fade in: "Packages running out", "Campaigns that could grow", "Campaigns under-delivering".

**NARRATOR:**
Every day, IndiaMART's lead report flags Ads sellers who need a call. Some packages are about to run out. Some campaigns are doing well enough to grow. Others are barely delivering. A relationship manager can't call all of them, and when they do, they first have to look the seller up.

---

## Scene 2 · VANI knows the seller first  (0:25–1:00)

**SCREEN:** Dashboard `/`. Show the call queue with Renew / Upsell / Improve badges. Click Miracle Tools; the seller page opens. Zoom on the `seller.md` card and the agent variables.

**NARRATOR:**
VANI reads that same report. For each seller it picks the most urgent reason to call: renew a package above 80 percent delivery, upsell a campaign between 50 and 80 percent, or fix one delivering under 50 percent in the last 28 days.
Before dialling, it builds a brief on the seller: their campaigns, leads, plan, the right category to pitch, and any past conversations. VANI speaks with Sarvam's voice models, and it already knows all of this before the seller picks up.
Let's hear three calls.

---

## Scene 3 · Call 1 · Renew  (1:00–2:05)

**SCREEN:** Seller page for Miracle Tools And Tackle LLP. Lower-third: "Tool Kits · 96 of 100 leads delivered · Renewal due". Then switch to the call view with captions (Hinglish line plus English subtitle). Show a small "tool" chip when VANI calls a tool.

**NARRATOR:**
Miracle Tools has received 96 of the 100 leads in its Tool Kits package.

**VANI:** Namaste! Main IndiaMART se VANI bol rahi hoon. Kya meri baat Miracle Tools And Tackle LLP se ho rahi hai? Aapke Tool Kits ads ki 96 percent delivery ho chuki hai, isliye renewal ke baare mein baat karni thi. Do minute baat kar sakte hain?
*(Hello! This is VANI from IndiaMART. Am I speaking with Miracle Tools? Your Tool Kits ads are 96% delivered, so I wanted to talk about renewal. Do you have two minutes?)*

**SELLER:** Haan boliye. Waise pichle mahine se leads aana hi band ho gaye hain.
*(Go ahead. Actually, the leads stopped coming last month.)*

**VANI:** Ji, aapke package ki 100 mein se 96 leads aa chuki hain, isliye ab leads ruk gayi hain. Renew karne par leads phir se shuru ho jaayengi. Kya aap isi plan ke saath continue karna chahenge?
*(Of your 100 leads, 96 have been delivered, which is why they've stopped. Renewing restarts them. Would you like to continue on the same plan?)*

`tool: get_package_status`

**SELLER:** Kitne ka hai?
*(How much is it?)*

**VANI:** Same plan 12 hazaar rupaye mein 100 leads ka hai.
*(The same plan is 12,000 rupees for 100 leads.)*

**SELLER:** Abhi itna budget nahi hai, thoda kam mein kuch hai?
*(I don't have that budget right now. Is there anything cheaper?)*

**VANI:** Ji, ek chhota option hai: 7,400 rupaye mein 60 leads. Isse aapki leads bina ruke aati rahengi.
*(Yes, there's a smaller option: 7,400 rupees for 60 leads. Your leads keep coming without a break.)*

**SELLER:** Theek hai, wahi kar dijiye.
*(OK, let's do that.)*

`tool: create_renewal_link`

**VANI:** Bahut badhiya. Maine 60 leads wale plan ka renewal link aapke WhatsApp par bhej diya hai. Kya aap abhi ek baar khol kar dekh lenge?
*(Great. I've sent the renewal link for the 60-lead plan to your WhatsApp. Could you open it now while I'm on the line?)*

**SELLER:** Haan, aa gaya.
*(Yes, I got it.)*

**VANI:** Shukriya! Toh 7,400 rupaye mein 60 leads ka plan, payment hote hi leads shuru ho jaayengi. Aapka din shubh ho!
*(Thank you! So that's the 60-lead plan for 7,400 rupees, and leads start as soon as you pay. Have a good day!)*

**SCREEN:** Outcome card: `call_outcome: renewal_agreed` · `renewal_plan: smaller` · `whatsapp_to_send: renewal_link`.

---

## Scene 4 · Call 2 · Upsell  (2:05–3:10)

**SCREEN:** Seller page for Sovisy India. Lower-third: "SMC Panel Tanks · 65 leads delivered · Pitch: RCC Water Tank, ~242 buyers/month".

**NARRATOR:**
Sovisy India's SMC Panel Tanks campaign is working. VANI looks for a category in the same family, one that buyers search for over 200 times a month, and finds RCC Water Tanks.

**VANI:** Namaste! Main IndiaMART se VANI bol rahi hoon. Kya meri baat Sovisy India Private Limited se ho rahi hai? Aapke SMC Panel Tanks ads achhe chal rahe hain, aur RCC Water Tank mein bhi aapke liye achhi demand dikh rahi hai. Do minute baat kar sakte hain?
*(Hello, this is VANI from IndiaMART. Am I speaking with Sovisy India? Your SMC Panel Tanks ads are doing well, and I see good demand for you in RCC Water Tanks too. Do you have two minutes?)*

**SELLER:** Haan ji, bataiye.
*(Yes, go ahead.)*

**VANI:** Aapke SMC Panel Tanks ads se ab tak 65 leads aa chuki hain. Isi wajah se main RCC Water Tank ke baare mein batana chahti thi.
*(Your SMC Panel Tanks ads have already brought 65 leads. That's why I wanted to tell you about RCC Water Tanks.)*

`tool: get_upsell_candidates`

**VANI:** Har mahine lagbhag 242 buyers RCC Water Tank dhoondhte hain. Yeh water tanks ki hi category hai, toh wahi buyers aapko dekhenge.
*(About 242 buyers search for RCC Water Tanks every month. It's in the same water-tank family, so the same buyers will see you.)*

**SELLER:** Hum RCC tank banate toh hain, par kya wahan bhi leads sahi aayengi? Kabhi kabhi galat enquiries aati hain.
*(We do make RCC tanks, but will the leads there be any good? Sometimes we get the wrong enquiries.)*

**VANI:** Achha sawaal hai. Ads sirf usi category ke buyers ko dikhte hain, aur aapke SMC tanks mein 20 buyers GST wale the. RCC mein bhi aisa hi target hoga. Kya main aapko WhatsApp par quote bhej doon?
*(Good question. Ads are shown only to buyers in that category, and 20 of your SMC tank buyers were GST-registered. RCC will be targeted the same way. Shall I send you a quote on WhatsApp?)*

**SELLER:** Haan bhej dijiye, dekh leta hoon.
*(Yes, send it. I'll take a look.)*

`tool: send_quote`

**VANI:** Ji, RCC Water Tank ke liye Premium plan, 18 hazaar rupaye, ka quote aapke WhatsApp par bhej diya hai. Main do din mein follow-up kar loon?
*(Done. The quote for RCC Water Tanks on the Premium plan, 18,000 rupees, is on your WhatsApp. Can I follow up in two days?)*

**SELLER:** Theek hai.
*(OK.)*

**VANI:** Shukriya! Toh quote WhatsApp par hai, aur main do din mein call karungi. Namaste!
*(Thank you! The quote is on WhatsApp and I'll call you in two days. Goodbye!)*

**SCREEN:** Outcome card: `call_outcome: upsell_interested` · `whatsapp_to_send: upsell_quote` · `callback_time: in two days`.

---

## Scene 5 · Call 3 · Improve  (3:10–4:15)

**SCREEN:** Seller page for Chirab Technologies. Lower-third: "Transformer Tester · 1 lead in 28 days · all 5 products already in the campaign". Show the Google Merchant Centre card: 5 live, 0 left to add.

**NARRATOR:**
Chirab Technologies got one lead in 28 days. VANI checks their real Google Merchant Centre listings. All five of their Transformer Testers are already in the campaign, so the fix is to list more.

**VANI:** Namaste! Main IndiaMART se VANI bol rahi hoon. Kya meri baat Chirab Technologies se ho rahi hai? Aapke Transformer Tester ads ki leads pichle 28 din mein kam aayi hain, unhe badhane ke kuch tareeke batane the. Do minute baat kar sakte hain?
*(Hello, this is VANI from IndiaMART. Am I speaking with Chirab Technologies? Your Transformer Tester ads got few leads in the last 28 days, and I have some ways to increase them. Do you have two minutes?)*

**SELLER:** Haan, sach mein, ek do enquiry hi aayi hai. Kya problem hai?
*(Yes, honestly, only one or two enquiries came in. What's the problem?)*

**VANI:** Pichle 28 din mein sirf 1 lead aayi hai. Aapne kya notice kiya, enquiries kam hain ya galat buyers aa rahe hain?
*(Only 1 lead came in the last 28 days. What have you noticed: fewer enquiries, or the wrong buyers?)*

**SELLER:** Enquiries hi nahi aa rahi.
*(The enquiries just aren't coming.)*

`tool: get_peer_top_products`

**VANI:** Aapke saare 5 Transformer Tester products already campaign mein hain. Itne kam products ke saath ad kam dikhta hai. Kya aap lagbhag 5 aur Transformer Tester products IndiaMART par list kar sakte hain, price aur photo ke saath?
*(All 5 of your Transformer Tester products are already in the campaign. With so few products, the ad shows less often. Could you list about 5 more Transformer Testers on IndiaMART, with price and photos?)*

**SELLER:** Haan, hamare paas aur models hain. Is hafte daal dete hain.
*(Yes, we have more models. We'll add them this week.)*

**VANI:** Bahut badhiya. Ek tip aur: enquiry aate hi ek ghante ke andar reply kariye, isse buyers zyada judte hain.
*(Great. One more tip: reply to each enquiry within an hour. Buyers respond much better.)*

`tool: schedule_callback`

**VANI:** Main do hafte baad call karke dekhungi ki naye products aur leads kaise chal rahe hain. Theek hai?
*(I'll call in two weeks to see how the new products and leads are doing. OK?)*

**SELLER:** Bilkul. Thank you.
*(Sure. Thank you.)*

**VANI:** Shukriya! Toh aap is hafte 5 naye products list karenge, aur hum do hafte mein baat karenge. Namaste!
*(Thank you! So you'll list 5 new products this week, and we'll talk in two weeks. Goodbye!)*

**SCREEN:** Outcome card: `call_outcome: products_approved` · `next_step: list 5 more products this week` · `callback_time: in two weeks`.

---

## Scene 6 · After the call  (4:15–4:45)

**SCREEN:** Chirab's seller page with **Conversations** expanded to show the stored transcript. Then `/whatsapp/118932009` with the RCC Water Tank quote already in the thread. Then Chirab's page again, where "VANI opens with" now picks up from this call.

**NARRATOR:**
After every call, VANI saves the full transcript, the outcome and a one-line summary. The renewal link and the quote are already on WhatsApp, where the seller can keep chatting with the same assistant.
That history goes into the next brief, so in two weeks VANI picks up where this call ended instead of starting from scratch.

---

## Scene 7 · Close  (4:45–5:00)

**SCREEN:** Title card: "VANI · knows the seller before it speaks". Under it: "Renew · Upsell · Improve · Built on Sarvam".

**NARRATOR:**
One report, three kinds of call, and every seller called with the right reason and the right numbers. That's VANI.

---

## Production notes

- **Captions:** show the Hinglish line large and the English subtitle smaller underneath. Tool chips (`tool: …`) appear for about 1 second at the point they're marked.
- **Voices:** VANI uses the same Sarvam voice as the live agent. Use a different male voice for each seller so the three calls sound distinct.
- **Mock parts:** plan prices, the renewal link, the quote and the WhatsApp delivery are mocked in the backend. The narration avoids claiming that payments are processed.
- **Real run option:** each call can also be played live in the browser at `/test?glid=<glid>`. Its transcript then appears under Conversations, and you can use that in Scene 6 instead of the scripted one.

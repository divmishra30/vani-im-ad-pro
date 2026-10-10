# VANI demo · transcript

## Scene 1 · The problem

**[00:00] Narrator:** Every day, IndiaMART's lead report flags Ads sellers who need a call.

**[00:04] Narrator:** Some packages are about to run out.

**[00:06] Narrator:** Some campaigns are doing well enough to grow.

**[00:09] Narrator:** Others are barely delivering.

**[00:11] Narrator:** A relationship manager can't call all of them, and when they do, they first have to look the seller up.

## Scene 2 · VANI knows the seller first

**[00:16] Narrator:** VANI reads that same report.

**[00:19] Narrator:** For each seller it picks the most urgent reason to call: renew a package above 80 percent delivery, upsell a campaign between 50 and 80 percent, or fix one delivering under 50 percent in the last 28 days.

**[00:30] Narrator:** Before dialling, it builds a brief on the seller: their campaigns, leads, plan, the right category to pitch, and any past conversations.

**[00:38] Narrator:** VANI speaks with Sarvam's voice models, and it already knows all of this before the seller picks up.

**[00:44] Narrator:** Let's hear three calls.

## Scene 3 · Call 1 · Renew

**[00:46] Narrator:** Miracle Tools has received 96 of the 100 leads in its Tool Kits package.

**[00:51] VANI:** Namaste! Main IndiaMART se VANI bol rahi hoon. Kya meri baat Miracle Tools And Tackle LLP se ho rahi hai? Aapke Tool Kits ads ki 96 percent delivery ho chuki hai, isliye renewal ke baare mein baat karni thi. Do minute baat kar sakte hain?  
*Hello! This is VANI from IndiaMART. Am I speaking with Miracle Tools? Your Tool Kits ads are 96% delivered, so I wanted to talk about renewal. Do you have two minutes?*

**[01:09] Seller:** Haan boliye. Waise pichle mahine se leads aana hi band ho gaye hain.  
*Go ahead. Actually, the leads stopped coming last month.*

**[01:14] VANI:** Ji, aapke package ki 100 mein se 96 leads aa chuki hain, isliye ab leads ruk gayi hain. Renew karne par leads phir se shuru ho jaayengi. Kya aap isi plan ke saath continue karna chahenge?  
*Of your 100 leads, 96 have been delivered, which is why they've stopped. Renewing restarts them. Would you like to continue on the same plan?*

`→ tool: get_package_status`

**[01:28] Seller:** Kitne ka hai?  
*How much is it?*

**[01:30] VANI:** Same plan 12 hazaar rupaye mein 100 leads ka hai.  
*The same plan is 12,000 rupees for 100 leads.*

**[01:34] Seller:** Abhi itna budget nahi hai, thoda kam mein kuch hai?  
*I don't have that budget right now. Is there anything cheaper?*

**[01:38] VANI:** Ji, ek chhota option hai: 7,400 rupaye mein 60 leads. Isse aapki leads bina ruke aati rahengi.  
*Yes, there's a smaller option: 7,400 rupees for 60 leads. Your leads keep coming without a break.*

**[01:46] Seller:** Theek hai, wahi kar dijiye.  
*OK, let's do that.*

`→ tool: create_renewal_link`

**[01:49] VANI:** Bahut badhiya. Maine 60 leads wale plan ka renewal link aapke WhatsApp par bhej diya hai. Kya aap abhi ek baar khol kar dekh lenge?  
*Great. I've sent the renewal link for the 60-lead plan to your WhatsApp. Could you open it now while I'm on the line?*

**[01:59] Seller:** Haan, aa gaya.  
*Yes, I got it.*

**[02:01] VANI:** Shukriya! Toh 7,400 rupaye mein 60 leads ka plan, payment hote hi leads shuru ho jaayengi. Aapka din shubh ho!  
*Thank you! So that's the 60-lead plan for 7,400 rupees, and leads start as soon as you pay. Have a good day!*

*Saved after the call:* `call_outcome: renewal_agreed` · `renewal_plan: smaller` · `whatsapp_to_send: renewal_link`

## Scene 4 · Call 2 · Upsell

**[02:14] Narrator:** Sovisy India's SMC Panel Tanks campaign is working.

**[02:17] Narrator:** VANI looks for a category in the same family, one that buyers search for over 200 times a month, and finds RCC Water Tanks.

**[02:25] VANI:** Namaste! Main IndiaMART se VANI bol rahi hoon. Kya meri baat Sovisy India Private Limited se ho rahi hai? Aapke SMC Panel Tanks ads achhe chal rahe hain, aur RCC Water Tank mein bhi aapke liye achhi demand dikh rahi hai. Do minute baat kar sakte hain?  
*Hello, this is VANI from IndiaMART. Am I speaking with Sovisy India? Your SMC Panel Tanks ads are doing well, and I see good demand for you in RCC Water Tanks too. Do you have two minutes?*

**[02:43] Seller:** Haan ji, bataiye.  
*Yes, go ahead.*

**[02:45] VANI:** Aapke SMC Panel Tanks ads se ab tak 65 leads aa chuki hain. Isi wajah se main RCC Water Tank ke baare mein batana chahti thi.  
*Your SMC Panel Tanks ads have already brought 65 leads. That's why I wanted to tell you about RCC Water Tanks.*

`→ tool: get_upsell_candidates`

**[02:55] VANI:** Har mahine lagbhag 242 buyers RCC Water Tank dhoondhte hain. Yeh water tanks ki hi category hai, toh wahi buyers aapko dekhenge.  
*About 242 buyers search for RCC Water Tanks every month. It's in the same water-tank family, so the same buyers will see you.*

**[03:05] Seller:** Hum RCC tank banate toh hain, par kya wahan bhi leads sahi aayengi? Kabhi kabhi galat enquiries aati hain.  
*We do make RCC tanks, but will the leads there be any good? Sometimes we get the wrong enquiries.*

**[03:13] VANI:** Achha sawaal hai. Ads sirf usi category ke buyers ko dikhte hain, aur aapke SMC tanks mein 20 buyers GST wale the. RCC mein bhi aisa hi target hoga. Kya main aapko WhatsApp par quote bhej doon?  
*Good question. Ads are shown only to buyers in that category, and 20 of your SMC tank buyers were GST-registered. RCC will be targeted the same way. Shall I send you a quote on WhatsApp?*

**[03:28] Seller:** Haan bhej dijiye, dekh leta hoon.  
*Yes, send it. I'll take a look.*

`→ tool: send_quote`

**[03:31] VANI:** Ji, RCC Water Tank ke liye Premium plan, 18 hazaar rupaye, ka quote aapke WhatsApp par bhej diya hai. Main do din mein follow-up kar loon?  
*Done. The quote for RCC Water Tanks on the Premium plan, 18,000 rupees, is on your WhatsApp. Can I follow up in two days?*

**[03:41] Seller:** Theek hai.  
*OK.*

**[03:44] VANI:** Shukriya! Toh quote WhatsApp par hai, aur main do din mein call karungi. Namaste!  
*Thank you! The quote is on WhatsApp and I'll call you in two days. Goodbye!*

*Saved after the call:* `call_outcome: upsell_interested` · `whatsapp_to_send: upsell_quote` · `callback_time: in two days`

## Scene 5 · Call 3 · Improve

**[03:53] Narrator:** Chirab Technologies got one lead in 28 days.

**[03:57] Narrator:** VANI checks their real Google Merchant Centre listings.

**[04:00] Narrator:** All five of their Transformer Testers are already in the campaign, so the fix is to list more.

**[04:05] VANI:** Namaste! Main IndiaMART se VANI bol rahi hoon. Kya meri baat Chirab Technologies se ho rahi hai? Aapke Transformer Tester ads ki leads pichle 28 din mein kam aayi hain, unhe badhane ke kuch tareeke batane the. Do minute baat kar sakte hain?  
*Hello, this is VANI from IndiaMART. Am I speaking with Chirab Technologies? Your Transformer Tester ads got few leads in the last 28 days, and I have some ways to increase them. Do you have two minutes?*

**[04:22] Seller:** Haan, sach mein, ek do enquiry hi aayi hai. Kya problem hai?  
*Yes, honestly, only one or two enquiries came in. What's the problem?*

**[04:28] VANI:** Pichle 28 din mein sirf 1 lead aayi hai. Aapne kya notice kiya, enquiries kam hain ya galat buyers aa rahe hain?  
*Only 1 lead came in the last 28 days. What have you noticed: fewer enquiries, or the wrong buyers?*

**[04:36] Seller:** Enquiries hi nahi aa rahi.  
*The enquiries just aren't coming.*

`→ tool: get_peer_top_products`

**[04:39] VANI:** Aapke saare 5 Transformer Tester products already campaign mein hain. Itne kam products ke saath ad kam dikhta hai. Kya aap lagbhag 5 aur Transformer Tester products IndiaMART par list kar sakte hain, price aur photo ke saath?  
*All 5 of your Transformer Tester products are already in the campaign. With so few products, the ad shows less often. Could you list about 5 more Transformer Testers on IndiaMART, with price and photos?*

**[04:53] Seller:** Haan, hamare paas aur models hain. Is hafte daal dete hain.  
*Yes, we have more models. We'll add them this week.*

**[04:58] VANI:** Bahut badhiya. Ek tip aur: enquiry aate hi ek ghante ke andar reply kariye, isse buyers zyada judte hain.  
*Great. One more tip: reply to each enquiry within an hour. Buyers respond much better.*

`→ tool: schedule_callback`

**[05:07] VANI:** Main do hafte baad call karke dekhungi ki naye products aur leads kaise chal rahe hain. Theek hai?  
*I'll call in two weeks to see how the new products and leads are doing. OK?*

**[05:14] Seller:** Bilkul. Thank you.  
*Sure. Thank you.*

**[05:16] VANI:** Shukriya! Toh aap is hafte 5 naye products list karenge, aur hum do hafte mein baat karenge. Namaste!  
*Thank you! So you'll list 5 new products this week, and we'll talk in two weeks. Goodbye!*

*Saved after the call:* `call_outcome: products_approved` · `next_step: list 5 more products this week` · `callback_time: in two weeks`

## Scene 6 · After the call

**[05:27] Narrator:** After every call, VANI saves the full transcript, the outcome and a one-line summary.

**[05:33] Narrator:** The renewal link and the quote are already on WhatsApp, where the seller can keep chatting with the same assistant.

**[05:38] Narrator:** That history goes into the next brief, so in two weeks VANI picks up where this call ended instead of starting from scratch.

## Scene 7 · Close

**[05:46] Narrator:** One report, three kinds of call, and every seller called with the right reason and the right numbers.

**[05:51] Narrator:** That's VANI.

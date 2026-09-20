# Does a ₹1,700/month Indic company-brain make sense?

**Question asked:** can we run on Cognee cheaply, sell at ~$20/month in India, and use Indic AI models for Indian context?

**Short answer:** the price works, the unit economics work *if you cap ingestion*, and the Indic models are a real differentiator but **not where you start**. Detail below, with the numbers and the sources.

---

## 1. The price point: $20/month is defensible

$20/month ≈ **₹1,700–1,800** (at roughly ₹85–90/USD — approximate, check the live rate before committing).

Research on Indian SaaS pricing puts the numbers here:

| Tier | Price | Who it targets |
|---|---|---|
| **Sustainable floor** | **₹999/month** | Below this you cannot cover support alone |
| **Sweet spot for the paid tier** | **₹1,499–2,999/month** | SMBs — the conversion target |
| Pro / revenue driver | ₹3,999–7,999/month | Growing businesses, API access |

**$20 lands squarely in the sweet spot.** Not so cheap it signals "toy", not so expensive that an Indian SMB procurement owner balks.

### Two things that matter more than the headline price

- **Annual billing converts better in India than monthly.** A plan at **₹7,999/year** outperforms ₹667/month even though it costs slightly more — Indian businesses budget by financial year (April–March) and think in lump sums. Offer both; default the UI to annual.
- **Freemium beats a free trial, decisively.** 14-day trials convert at **3–6%** in India versus **8–15%** for well-designed freemium. Indian SMB buyers don't respond to countdown urgency; a trial that expires while they're busy just means they never come back.

---

## 2. The unit economics: they work, but only with an ingestion cap

Cognee's actual pricing (verified, Sept 2026):

| Plan | Price | What you get |
|---|---|---|
| **Free** | **$0** | 1M tokens, 1 workspace, **unlimited users, unlimited API calls** |
| **Standard** | **$1.00 / 1M tokens** + **$5 per additional workspace/month** | Unlimited workspaces, Slack/Notion/Linear/Drive integrations, code indexing |
| **Enterprise** | Contact | BYOC, dedicated support |
| **Self-hosted** | **Free forever** | Apache-2.0 / MIT — you run it on your own stack |

**The critical fact: Cognee bills per TOKEN PROCESSED, not per seat.** So cost scales with how much data a customer ingests, not how many people use it. That is unusual and it cuts both ways.

### Per-customer monthly cost at $20/month pricing

| Item | Assumption | Cost |
|---|---|---|
| Workspace | 1 per customer | $5.00 |
| Ingestion | 100 documents × ~5K tokens = 500K tokens | $0.50 |
| Queries | 100 queries × ~15K tokens = 1.5M tokens | $1.50 |
| **Cognee subtotal** | | **~$7.00** |
| Hosting share | Render, shared across customers | ~$1.00 |
| **Total cost to serve** | | **~$8.00** |

**At $20/month that's ~60% gross margin** — ~$12 per customer. Workable, not luxurious.

### Where it breaks

**One heavy customer inverts the model.** Someone who bulk-ingests 5M tokens of documents costs **$5 on ingestion alone** before they ask a single question. Two such customers and you're at break-even on them.

**So: cap ingestion per tier.** This is standard practice, not a limitation you're apologising for:

- Free: 1M tokens ingested/month (Cognee's own free allowance)
- ₹1,700/month: **5M tokens ingested/month**, unlimited queries
- Pro: 25M tokens

State the cap on the pricing page. It makes the cost predictable and it gives heavy users an obvious reason to upgrade.

**Do not sell "unlimited ingestion" at a flat price.** With token-based upstream billing, that is a business that dies quietly.

---

## 3. The Indic model question: real, but the wrong first move

**The landscape is better than it was.** Of **35 Indian AI models tracked, 24 have open weights** — including genuinely usable ones:

| Model | Org | Size | Indic languages | Weights |
|---|---|---|---|---|
| **Param2** | BharatGen | 17B | 22 | **Open** |
| **Sarvam-M** | Sarvam AI | 24B | 10 | **Open** |
| **Krutrim-2** | Krutrim | 12B | 11 | **Open** |
| **Sarvam-Translate** | Sarvam AI | 4B | 22 | **Open** |
| Sarvam 105B / 30B | Sarvam AI | 105B / 30B | 22 | Closed (API) |

So the option exists. Here is why I would **not** lead with it:

**1. Your documents are mostly English anyway.** The artefacts a company brain actually needs to connect — contracts, MSAs, policies, incident tickets, QBR notes — are written in English at Indian B2B companies, because they are legal and commercial documents. An Indic model does not help you read an MSA.

**2. Self-hosting a 17–24B model is a GPU bill you cannot pay at low volume.** A 24B model needs roughly 24GB VRAM quantised, 48GB at FP16. Always-on GPU in India runs into the tens of thousands of rupees per month. That is only sensible past a few hundred paying customers — the opposite of where you start.

**3. Cognee's cloud owns the model.** On the cloud tenant you do not choose the LLM. To use Param2 or Sarvam-M you must **self-host Cognee** (free) and point it at your own model endpoint via `LLM_PROVIDER`. That is a real architectural change: you take on the vector store, the graph store and the database yourself. Doable — it is exactly the trade this project documented — but it is a different business to run.

### Where Indic models genuinely win

Not "Indian context" as a vague claim. These specific cases:

- **Regional-language documents** — Hindi/Tamil/Bengali invoices, notes, correspondence
- **Vernacular support threads** — WhatsApp and chat where customers write in their own language
- **Voice notes** — the single most Indian input format, and speech models here are strong (AI4Bharat's IndicConformer, Sarvam's Saaras/Bulbul)

**Sequence it:** start on Cognee Cloud at $1/1M tokens with no infrastructure. Add an Indic model when a paying customer's content is actually regional-language. Sell it as the answer to *their* problem, not as a feature on a spec sheet.

---

## 4. What actually differentiates you in India

The research is blunt about this: **the winning position is not "we're cheaper", it is "we're built for India."** Cheaper-than-Zoho is a losing frame.

Concretely, that means:

| Requirement | Why it matters |
|---|---|
| **GST-compliant invoicing** (18%, CGST/SGST or IGST split, your GSTIN) | An Indian B2B finance team **cannot process a payment without a tax invoice**. Missing this looks like churn but is actually an invoice failure. |
| **Capture GSTIN at signup** | Same reason. It must be on the form. |
| **UPI AutoPay for recurring** | UPI dominates under ₹1,000. Customers who pay one-offs by UPI will drop off at checkout if UPI AutoPay isn't offered. |
| **Razorpay Subscriptions** | The default for Indian SaaS — handles UPI AutoPay mandates and generates GST invoices automatically. Chargebee only becomes worth its ~0.75% of revenue past roughly ₹5 lakh MRR. |
| **INR pricing, no conversion surprises** | Plus support in IST by people who know Indian business context. |
| **Regional-language ingestion** | The genuine wedge against Zoho/QuickBooks — CA firms recommend what handles local compliance correctly. |

The strongest version of your pitch: *"built for India"* commands a premium from buyers who have been burned by US tools needing workarounds.

---

## 5. What I would actually do

1. **Price at ₹1,499–1,999/month, billed annually at ₹15,999–19,999.** In the researched sweet spot; annual-first because that is what converts here.
2. **Free tier with 1 workspace and 1M tokens ingested** — Cognee's own free allowance, so your pilot costs nothing. Make collaboration and export the friction that drives upgrades.
3. **Cap ingestion per tier** (5M / 25M tokens). Never sell unlimited ingestion on flat pricing.
4. **Start on Cognee Cloud, not self-hosted.** $1/1M tokens with zero infrastructure beats a GPU bill you cannot amortise. Self-hosting is the move at scale, not at zero.
5. **Do not lead with Indic models.** Lead with GST invoicing, UPI AutoPay, INR pricing and IST support — the things that block a purchase. Add Indic models when a customer's content demands it.
6. **Use the free 1M tokens to run three real pilots** before building a pricing page. The research is explicit: test the price with real prospects rather than benchmarking against local software expectations, which is how Indian founders underprice.

---

## The honest verdict

| Question | Verdict |
|---|---|
| Can Cognee be run cheaply? | **Yes.** Free tier is generous; $1/1M tokens is low; self-hosting is free if you take on the infrastructure. |
| Does $20/month work in India? | **Yes** — it sits in the researched ₹1,499–2,999 sweet spot. Bill annually. |
| Do the unit economics work? | **Yes at ~60% gross margin — but only with an ingestion cap.** Token-based upstream billing punishes unlimited plans. |
| Are Indic models a good idea? | **Yes, but not first.** They help with regional-language documents, vernacular chat and voice — not with the English contracts that matter most. The purchase blockers are GST, UPI and IST support. |

**Sources:** Cognee pricing page (cognee.ai/pricing, Sept 2026) · Indian AI model tracker (indianaicommunity.com, Sept 2026) · Rajesh R Nair, *SaaS Pricing for the Indian Market in 2026* (Apr 2026), which supplied the PPP ratio (~0.27), the ₹999 floor, the ₹1,499–2,999 sweet spot, the trial-vs-freemium conversion figures and the GST/UPI/Razorpay specifics.

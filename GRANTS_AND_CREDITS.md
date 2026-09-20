# Startup grants and credits: what to claim, and what to actually do with it

**Question:** what startup grants/credits are available, and how do I use them *effectively* for this project?

**The short version:** cloud credits are the easy win and you should claim all three majors — but for **this** product the highest-value items are not credits at all. They are **SAMRIDH** (built for software product startups), **GeM Startup Runway** (a revenue channel), and **DPIIT recognition** (which unlocks everything else). And there is one strategic decision the credits force: whether to keep DeepSeek or move the model onto a cloud whose credits you hold.

---

## 1. Cloud credits — claim all three, they do not exclude each other

| Program | Self-serve tier | Top tier | AI models the credits buy |
|---|---|---|---|
| **Microsoft for Startups** | **$1,000 at signup → $5,000 after verification** | $100k–150k via Investor Network referral | **Azure OpenAI (GPT)** + Azure AI Foundry |
| **Google for Startups** | ~$2,000 pre-funding | **$200k over 2 years**; **$350k AI-first** | Vertex AI + **Gemini** |
| **AWS Activate** | Founders path (small) | **~$100k** Portfolio, needs a VC/accelerator Org ID | **Bedrock** — Claude, Llama, Mistral, Nova |

**Start with Microsoft.** It is the only one with a meaningful self-serve rung — **$5,000 after business verification, no investor required.** Google's ~$2,000 is trivial; AWS's real tier needs someone to vouch for you.

**Then AWS**, on whichever path you qualify for — accelerator-backed teams get the Portfolio unlock from a single email to their program manager.

**Google last**, the moment you have equity funding or a credible AI-first story.

### ⚠️ What cloud credits do *not* buy for this project

**Your model runs on DeepSeek, which is not on any of these clouds.** So a $100k AWS credit buys you Postgres, compute and storage — but **not** the inference that is your actual per-customer cost.

**That forces a real decision, and it is the most important thing in this document:**

| Option | What it means |
|---|---|
| **Keep DeepSeek** | Cheapest per token ($0.15/$0.60 per 1M, 50× cheaper cache hits). Cloud credits pay for infra only — which is only ~$14/month. **A $100k credit would take decades to spend.** |
| **Move to Bedrock / Vertex / Azure OpenAI** | Your inference is now covered by credits. But Claude, Gemini and GPT all cost **10–30× more per token** than DeepSeek. |

**The honest read:** for a product whose only real cost is tokens, **cloud credits are worth far less than they look.** $100k of AWS credit against a $14/month infrastructure bill is not a $100k gift — it is a rounding error. The credits only become valuable if you deliberately move the model onto that cloud, and then you are trading a 10–30× per-token increase for a fixed credit that expires.

**Do the arithmetic for your own volumes before switching models to "use up" a credit.** Credits expire; a permanently worse unit cost does not.

---

## 2. Indian government schemes — where the real money is

Amounts are exact, from a June 2026 directory of 69 central schemes.

| Scheme | Amount | Why it fits **this** project |
|---|---|---|
| **SAMRIDH** (MeitY) | **₹40 lakh**, plus **equal matching private investment up to ₹40 lakh** | ⭐ **Built specifically for software product startups.** The closest match to what you are building. Route: MeitY accelerators. |
| **SISFS** (Startup India Seed Fund) | **₹20 lakh grant + ₹50 lakh convertible debt** | The standard early path. Grant for PoC, debt for market entry. Route: approved incubators. |
| **MeitY GENESIS** | **₹10 lakh** early-stage; **up to ₹1 crore** deep-tech | ₹490 crore outlay. Aimed at Tier-II/III cities. |
| **NGIS** (STPI) | Seed/risk funding **up to ₹25 lakh** | MeitY, 300 startups, ₹95 crore outlay. |
| **NIDHI-SSP** (DST) | **Up to ₹1 crore** | Via DST-supported TBIs. |
| **SIPP** | **80% patent fee rebate, 50% trademark/design** | If you patent the tenant-isolation or multi-hop retrieval method, this covers most of the cost. |

### The three non-cash items that matter more than the money

**1. DPIIT recognition (Startup India registration).** Almost every scheme above requires it. It is free, it is the prerequisite for everything else, and it also brings **tax benefits and self-certification**. **Do this first — it costs nothing and gates the rest.**

**2. GeM Startup Runway — government procurement access.** This is a **revenue channel, not a grant.** For a company-brain product, government departments, PSUs and municipal bodies are real buyers with real document chaos and a mandate to digitise. A procurement route into them is worth more than a ₹20 lakh grant.

**3. Credit guarantee, not cash — CGSS / CGTMSE.** Up to ₹20 crore and ₹10 crore guarantee cover respectively. Not a grant, but it means a bank will lend without collateral, which matters once you have revenue and need working capital.

---

## 3. How to use this effectively for *this* project

The trap with grants is spending six months applying and building nothing. Here is a sequence that does not waste your time:

### Do now (weeks, not months, near-zero effort)

1. **Register for DPIIT recognition.** Free, fast, and it is the gate for every scheme below.
2. **Claim Microsoft for Startups $1,000 → $5,000.** Self-serve, no investor needed. Put the app on Azure App Service or a VM.
3. **Claim the GitHub Student Pack items** (Clerk, Heroku, Blackfire, Doppler) while you are still enrolled — see `STUDENT_PACK_STACK.md`. This is your **build-and-validate** environment at ~$5–20/month.

### Do when you have a working product and a first user

4. **Apply to SAMRIDH.** It is the one scheme written for software products, and the matching-investment structure means you also get an accelerator relationship, not just cash.
5. **Apply to SISFS through an incubator.** Note the trap: **it caps prior government funding at ₹10 lakh**, so do not take other government money first and disqualify yourself.
6. **File AWS Activate** on whatever path you qualify for.

### Do when you have revenue

7. **Patent the tenant-isolation method** (or the multi-hop retrieval approach) and claim the **SIPP 80% rebate**. A patent on how you isolate one company's knowledge graph from another's is defensible and commercially meaningful.
8. **Get on GeM Startup Runway** and go after government buyers.
9. **Use CGSS/CGTMSE** to get collateral-free working capital instead of diluting.

---

## 4. The traps, stated plainly

**Grants take months and are milestone-linked.** SISFS and SAMRIDH are audited, disbursed in tranches, and tied to milestones. They are not a way to fund the next three months.

**Cloud credits expire and the clock starts at approval, not at launch.** AWS credits commonly lapse within months to ~2 years; Google's big tiers cover year one fully but only *part* of year two. **Apply when you can actually burn the credit**, not the day you incorporate.

**Lock-in is the actual product these programs sell.** Microsoft's top tier spreads over five years and bundles GitHub Enterprise and Microsoft 365 — designed to make your company Microsoft-shaped. Keep your infrastructure portable: containers, standard Postgres, S3-compatible storage. Accept lock-in only where the managed service is genuinely better.

**Eligibility traps that silently disqualify you:**
- SISFS caps **prior government funding at ₹10 lakh**
- SPARSH requires an entity **under 3 years old**
- TDF requires **50% Indian ownership**
- Most schemes need **DPIIT recognition first**

**One decision to make deliberately:** whether to move off DeepSeek. It is your only real per-customer cost, and it is 10–30× cheaper than the models the cloud credits buy. **Do not switch models just to consume a credit** — model the volumes first.

---

## Verdict

| Question | Answer |
|---|---|
| Claim the cloud credits? | **Yes, all three** — they do not exclude each other. Start with Microsoft's $5,000 self-serve rung. |
| Will they cover this project? | **Only infrastructure (~$14/month).** Your real cost is DeepSeek tokens, which no cloud credit covers. |
| Biggest money available? | **SAMRIDH (₹40L + ₹40L matching)** — the only scheme written for software product startups. Then **SISFS (₹20L grant + ₹50L debt)**. |
| Most valuable non-cash item? | **DPIIT recognition** — free, gates everything, takes weeks not months. Then **GeM Startup Runway**, which is a revenue channel. |
| What to do first? | DPIIT registration, Microsoft's $5,000 rung, and the student pack. All near-zero effort. |
| What not to do? | Do not spend months applying before you have a product, and **do not switch models just to burn a credit.** |

**The honest summary:** for a product whose only real cost is inference, grants and credits are worth less than they appear — a $100k cloud credit against a $14/month bill is not $100k of value. The items that actually change your trajectory are **DPIIT recognition, SAMRIDH, and GeM procurement access**, because they either unlock everything else or bring revenue rather than credits.

**Sources:** AWS Activate (aws.amazon.com/startups/credits) · Microsoft for Startups and Google for Startups comparison (perkstack.co, July 2026) · Indian central government schemes directory, 69 schemes (companyavenueadvisory.com, June 2026) · GitHub Student Developer Pack (education.github.com/pack) · DeepSeek pricing (aipricing.guru, Sept 2026).

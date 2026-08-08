# Deep Research Summary: Hosting & Domains for Ahron Darnell Personal Brand

**Date:** 2026-08-07  
**Project:** Compliance consultant (SOC, PCI, HIPAA) + visual artist personal brand site  
**Requirements:** Marketing-heavy, art/media, lead generation, secure/reliable, 80s-90s retro/hacker/punk aesthetic, AI-bot friendly, no-cost/low-cost hosting

---

## 1. Free Hosting Tiers (Viable for Professional Sites)

| Platform | Key Limits | Business Use? | Verdict |
|----------|-----------|---------------|---------|
| **Cloudflare Pages** | 500 builds/mo, 100 custom domains, unlimited bandwidth, 20K files | Yes (Free is fine for static) | **BEST FREE OPTION** - unlimited bandwidth, edge CDN, Workers integration |
| **Vercel Hobby** | 100GB bandwidth, 1M requests, 4hr CPU, 60s function timeout | **NO** - commercial use prohibited | Not suitable for business without $20/seat Pro upgrade |
| **Netlify Free** | 300 credits/mo (~15GB bandwidth), 1 concurrent build, sites pause when exhausted | Yes (but risky) | Use only if traffic is very low; sites go down when credits exhausted |
| **GitHub Pages** | 100GB bandwidth (soft), 1GB site size, 10 builds/hr | **NO** - not for business | Violates ToS for commercial sites |
| **Firebase Hosting** | 10GB storage, 10GB/mo transfer (360MB/day soft cap) | Yes (Spark plan) | Decent for static sites, but low transfer limits |
| **Render Free** | 5GB bandwidth, 500 build mins, 750 instance hrs/mo | Partially (static sites OK) | Web services spin down after 15min; static sites don't |
| **Fly.io** | **NO FREE TIER** - only 2hr/7day trial | N/A | Not viable for no-cost hosting |
| **Neocities** | 1GB storage, 200GB bandwidth | Yes (personal) | Retro/hacker aesthetic aligns with brand; limited to static files |
| **Glitch** | **SHUT DOWN** July 2025 | N/A | Not available |
| **Surge.sh** | Unlimited publishing, custom domains, basic SSL | Yes | Simple CLI-based static hosting; $30/mo for Pro features |

**Recommendation:** Cloudflare Pages Free is the strongest no-cost option. Pair with Cloudflare Registrar and Cloudflare Web Analytics for a fully free stack.

---

## 2. Low-Cost Paid Hosting ($1-$10/month)

| Platform | Starting Cost | Bandwidth | Storage | Build | SSL | CDN |
|----------|--------------|-----------|---------|-------|-----|-----|
| **Cloudflare Pages Pro** | $20/mo | Unlimited | 20K files | 5 concurrent, 5K/mo | Free | Cloudflare Edge |
| **Vercel Pro** | $20/seat | 1TB | Blob: 50GB | 24K min/mo, 1 concurrent | Auto | Vercel Edge |
| **Netlify Pro** | $20/mo | ~150GB equiv | Blob/DB | 3 concurrent, 3K credits | Free | Netlify Edge |
| **DigitalOcean App** | $5/mo | 50GB | - | Static free | Auto | Global CDN |
| **Linode Akamai** | $5/mo | 1TB bundled | - | Self-managed | Self | Not included |
| **Fly.io** | ~$2-5/mo | 160GB free, $0.02/GB | 3GB free | VMs | Self | 30+ regions |
| **Render Pro** | $25/mo flat | 25GB, $0.15/GB | - | 1K build mins | Auto | CDN included |
| **Cloudflare R2 + Workers** | $5/mo min | Free egress | 10GB free | Via Workers | Via Cloudflare | Cloudflare Edge |
| **Supabase** | $25/mo | 250GB | 100GB | Edge Functions | - | Edge |
| **Deno Deploy** | $20/mo | 200GB | 1GB KV | 5M requests | Auto | Edge network |

**Recommendation for $1-10/mo range:** DigitalOcean App Platform Free (3 static sites) or a $5-10 VPS-like setup. For actual production with custom domain and SSL on a budget, Cloudflare Pages Pro at $20/mo is the most feature-complete.

---

## 3. Domain Registrars & TLD Options

### Registrars (Best for Total Cost of Ownership)

| Registrar | .com Renewal | WHOIS Privacy | DNSSEC | API | Notes |
|-----------|-------------|---------------|--------|-----|-------|
| **Cloudflare** | $10.44 | Free | Free | Yes | At-cost, no markup, 423 TLDs |
| **Porkbun** | $11.08 | Free | Free | Yes | Near-wholesale, clean UI, 2M+ domains |
| **Namecheap** | $13.98 | Free | Free | Yes | Lowest first year ($5.98), broad TLD selection |
| **NameSilo** | ~$11.05 | Free | Free | Yes | Portfolio discount program |
| **Gandi** | ~$39.98 | Free | Yes | Yes | Ethical stance, higher pricing |
| **OVH** | ~$13.99 | Free | Yes | Limited | EU-based |

**Recommendation:** Cloudflare Registrar for TLDs they support (best price, integrated DNS). Porkbun for everything else.

### TLD Pricing (Annual, Approximate)

| TLD | Typical Price | Best For | Notes |
|-----|--------------|----------|-------|
| .com | $10-12 | General business | Most recognized, safest choice |
| .net | $12-15 | Tech/alternate | Established alternative |
| .org | $10-13 | Non-profit/credibility | Trusted for organizations |
| .io | $30-50 | Tech/startups | Premium pricing, popular in tech |
| .dev | $12-18 | Developer/security | Requires HTTPS |
| .xyz | $10-12 | Modern/generic | Cheap, popular with startups |
| .art | $13-25 | Creative/artistic | Fits visual art side |
| .tech | $40-60 | Technology | Higher registry pricing |
| .site | $20-28 | General | Moderate pricing |
| .consulting | $25-42 | Consulting firms | Fits compliance consulting |
| .healthcare | $33-68 | Medical/health | Fits HIPAA consulting |
| .finance | $33-50 | Financial services | Fits PCI consulting |
| .security | **$2,000+** | Security firms | VERY expensive premium TLD |
| .hacker | Check registrar | Hacker/tech culture | Check availability |
| .punk | Check registrar | Punk/alternative culture | Check availability |

**Brand Recommendation:** Primary domain should be `[name].com` or `[name].consulting` for professionalism. Consider `.art` or `.punk` as a secondary/redirect domain for the artistic side.

---

## 4. Static-Site-Friendly CDN/Edge Services

### CDN Comparison

| Service | Free Tier | Paid Starting | Image Optimization | Key Feature |
|---------|-----------|---------------|-------------------|-------------|
| **Cloudflare** | Unlimited bandwidth | $20/mo/zone | Polish (Pro+), Images ($5/100K stored) | 330+ PoPs, free WAF, DDoS |
| **Bunny CDN** | $1/mo minimum | $1/mo + $0.01/GB | Optimizer: $9.50/site/mo | Cheapest pay-as-you-go, 119 PoPs |
| **Netlify Edge** | Included | Included with hosting | Image CDN included | Built-in, framework integrations |
| **Vercel Edge** | Included | Included with hosting | 5K free transformations | Built-in, Next.js native |
| **Fastly** | No free tier | Enterprise | Enterprise pricing | High-performance, expensive |

### Image Optimization

- **Cloudflare Images:** 5K free transformations/mo, then $0.50/1K remote or $5/100K stored + $1/100K delivered
- **Cloudflare Polish:** Pro+ only ($20/mo) - lossless/lossless compression, WebP/AVIF
- **Netlify Image CDN:** Included, on-demand transformations, AVIF/WebP auto-negotiation
- **Vercel Image Optimization:** 5K free/mo, then $0.05-0.08/1K transformations
- **Bunny Optimizer:** $9.50/site/mo, unlimited, works with any CDN

### Form Handling

| Service | Free Tier | Paid | Notes |
|---------|-----------|------|-------|
| **Netlify Forms** | **UNLIMITED FREE** (as of Apr 2026) | Included | Spam protection, email notifications |
| **Vercel** | None native | - | Requires Server Actions, API routes, or Formspree |
| **Formspree** | Free tier | From $10/mo | Email submissions, spam filtering, integrations |
| **Cloudflare Turnstile** | 20 widgets, unlimited challenges | Enterprise | Bot protection, privacy-focused |
| **Getform** | Free tier | From $9/mo | Form backend with spam filtering |
| **Basin** | Free tier | From $5/mo | Simple form handling |

---

## 5. Security Considerations for Compliance Consultant Brand

### Essential Security Headers & Configurations

| Control | Implementation | Priority |
|---------|---------------|----------|
| **HTTPS** | Enforce via HSTS header, auto-SSL from host | Critical |
| **HSTS** | `max-age=31536000; includeSubDomains; preload` | Critical |
| **CSP** | Content Security Policy to prevent XSS | High |
| **DNSSEC** | Enable at registrar (free with Cloudflare/Porkbun) | High |
| **DDoS Protection** | Built-in with Cloudflare/Netlify/Vercel | High |
| **CAA Records** | Restrict which CAs can issue certificates | Medium |
| **Cookie Security** | Secure, HttpOnly, SameSite flags | High |
| **Audit Logging** | Cloudflare Analytics, host logs | Medium |

### Privacy-First Analytics (Cookie-Banner Free)

| Tool | Free Tier | Paid Starting | Self-Host | Open Source |
|------|-----------|---------------|-----------|-------------|
| **Cloudflare Web Analytics** | **FREE** | Free | No | No |
| **Plausible** | 30-day trial | $9/mo (10K PV) | Yes (AGPL) | Yes |
| **Umami** | 1M events/mo | $9/mo (100K events) | Yes (MIT) | Yes |
| **Fathom** | 7-day trial | $15/mo (100K PV) | No | No |

**Recommendation:** Cloudflare Web Analytics (free, if on Cloudflare) or Plausible ($9/mo, best all-around).

### Compliance Brand Signals

- HTTPS + HSTS + modern TLS = baseline competence signal
- Security headers audit (CSP, HSTS, DNSSEC) demonstrates attention to detail
- SOC 2 awareness in site content (even if not certified yet)
- Privacy-first analytics choice signals data protection values
- Regular content updates with `dateModified` timestamps

---

## 6. All-in-One Website Builders

| Platform | Starting Cost | Flexibility | Exportability | SEO | Best For |
|----------|--------------|-------------|---------------|-----|----------|
| **Webflow** | $14/mo (annual) | High (visual dev) | HTML/CSS/JS only (paid) | Good | Designers, custom layouts |
| **Squarespace** | $16/mo (annual) | Medium | **NO EXPORT** | Good | Non-technical users, beautiful templates |
| **Carrd** | $9/year | Low (one-page) | Plus plan only | Limited | Simple link-in-bio, landing pages |
| **Gumroad** | No monthly fee | Low | No | N/A | Digital product sales, not websites |
| **Shopify Lite** | $9/mo | Low (ecommerce) | No | Ecommerce-focused | Simple online stores |

**Recommendation:** For a marketing-heavy, multi-page site with art/media and lead generation, Webflow is the best builder option if avoiding code. However, for maximum control and retro/hacker aesthetic customization, a static site generator (Astro, Next.js, 11ty) hosted on Cloudflare Pages or Vercel is superior.

---

## 7. AI Crawler Optimization Checklist

The site must attract AI bots (GPTBot, ClaudeBot, PerplexityBot) for modern search visibility:

1. **Use Static Site Generation (SSG)** - Pre-rendered HTML visible to all crawlers
2. **Avoid Client-Side Rendering for content** - 69% of AI crawlers don't execute JavaScript
3. **Implement `llms.txt`** - AI-specific content guide at root domain
4. **Add Schema.org JSON-LD** - Organization, Article, Product, FAQPage, BreadcrumbList
5. **Structured content** - H1→H2→H3 hierarchy, 200-400 word modular sections
6. **XML sitemap** - Auto-generated, referenced in robots.txt
7. **Allow AI crawlers** in robots.txt (GPTBot, ClaudeBot, PerplexityBot, Google-Extended)
8. **Fast Core Web Vitals** - LCP < 2.5s, INP optimized, TTFB < 200ms
9. **Fresh content** - Update quarterly, visible `dateModified` timestamps
10. **Image optimization** - WebP/AVIF formats, proper alt text

---

## 8. Recommended Stack (No-Cost Priority)

### Option A: Maximum Free (Cloudflare Ecosystem)
- **Hosting:** Cloudflare Pages (Free)
- **Domain:** Cloudflare Registrar (~$10.44/yr for .com)
- **CDN/DNS:** Cloudflare (free)
- **Analytics:** Cloudflare Web Analytics (free)
- **Forms:** Netlify Forms via Netlify (free unlimited submissions) OR Formspree free tier
- **Image Optimization:** Cloudflare Images (5K free transformations/mo)
- **Bot Protection:** Cloudflare Turnstile (free)
- **Total Monthly Cost:** $0 (plus ~$0.87/mo domain amortized)

### Option B: Best Developer Experience (Vercel)
- **Hosting:** Vercel Pro ($20/seat/mo) - required for commercial use
- **Domain:** Porkbun or Cloudflare
- **Analytics:** Vercel Analytics (bundled) or Plausible ($9/mo)
- **Forms:** Server Actions + Email API or Formspree
- **Total Monthly Cost:** $20-29/mo

### Option C: Balanced Low-Cost
- **Hosting:** Netlify Pro ($20/mo) OR Cloudflare Pages Pro ($20/mo)
- **Domain:** Porkbun (~$11/yr)
- **Analytics:** Plausible ($9/mo) or Cloudflare Web Analytics (free)
- **Forms:** Netlify Forms (unlimited free)
- **Total Monthly Cost:** $20-29/mo

---

## 9. Key Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Vercel Hobby commercial use ban | Use Pro plan or switch to Cloudflare Pages |
| Netlify credit exhaustion | Monitor usage, enable auto-recharge, or switch to Cloudflare |
| Free tier service changes | Avoid vendor lock-in, use static export where possible |
| Domain renewal price hikes | Use Cloudflare/Porkbun for flat renewal pricing |
| AI crawler blocking | Audit robots.txt, ensure SSR/SSG, test with JS disabled |
| Cookie consent requirements | Use privacy-first analytics (Plausible/Umami/CF Analytics) |
| Form spam | Use Netlify Forms, Turnstile, or Formspree spam filtering |

---

## 10. Evidence Paths

All raw research notes with source URLs, dates, and detailed findings are stored in:
- `/home/ahron/codespace/artifacts/deep-research/hosting-domains/raw_notes.json`

This summary was generated from live web research conducted on 2026-08-07 using websearch and webfetch tools against official documentation, pricing pages, and trusted community sources.

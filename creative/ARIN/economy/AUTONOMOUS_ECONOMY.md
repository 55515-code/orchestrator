# Economy, Pricing, and Release System

Goal: make the finished digital book inexpensive to buy while recovering production cost and creating reasonable ongoing income.

## Ledger
Track real costs by task:
- model/API usage
- image generation
- editing/QA
- formatting
- hosting/domain
- storefront/payment fees
- optional advertising
- human hours as a separate non-cash metric

Calculate:
`net_per_sale = price - platform_fee - payment_fee - delivery_variable_cost`

Calculate break-even units for:
1. cash costs only
2. cash costs + a configurable value for creator labor

Do not fabricate fee schedules. Store current platform assumptions with source/date and make them replaceable.

## Pricing experiments
Prepare scenarios rather than hard-code a price:
- low-friction launch price
- standard digital price
- supporter/pay-what-you-want option where supported
- bundle with art/notes later

Rank options by buyer friction, net revenue, control, discoverability, and administrative overhead.

## Release gate
The system may autonomously:
- build storefront-ready metadata
- prepare descriptions, excerpts, cover sizes, keywords, ISBN decision notes
- create upload packages
- model pricing
- stage analytics
- draft launch material

It may **not** autonomously:
- create financial obligations
- accept platform terms
- set up payout/tax identities
- publish the book
- spend on advertising
without explicit human approval.

## Promotion engine
After manuscript lock, derive promotion from the work rather than inventing unrelated marketing:
- poster variants
- short visual excerpts
- character/system dossiers
- ARIN terminal fragments
- quote cards
- making-of/process material
- sample chapter
- launch page copy

Use an experiment queue. Each experiment gets hypothesis, channel, asset, cost ceiling, metric, stop condition, and result. Prefer zero/low-cost organic tests before paid promotion.

# Client delivery checklist (2 days)

This repo is the reusable base. For the LaborX job, the remaining work is
configuration + deployment, not new features.

## Day 0 — kickoff message (send immediately after acceptance)

Ask the client for exactly these items in one message:

1. **BotFather token** for the shop bot (they create it; never share it in a
   public channel — use LaborX chat or a password manager link).
2. **Catalog**: categories, product names, descriptions, prices, stock, photos.
   A spreadsheet or a list in chat is fine.
3. **Payment methods**: e.g. USDT TRC20 address, BTC address, cash on delivery
   wording. The bot only *displays* instructions.
4. **Currency** and shop name.
5. **Admin Telegram user IDs** (numeric, from @userinfobot).
6. **Delivery address rules** — any fields they want beyond name/phone/address
   (the template has those three; extra fields are a small change).
7. **Hosting choice**: their VPS, or a $4–6/month VPS arranged by us.

## Day 1 — configure and deploy

- [ ] Create `.env` from `.env.example`; set token, admin IDs, shop name,
  currency, payment methods.
- [ ] Load the client catalog. Either import their spreadsheet with a short
  script based on `scripts/seed_demo.py`, or use `/addcategory` and
  `/addproduct` in chat.
- [ ] Set product photos with `/setphoto <id> <file_id or URL>`.
- [ ] Deploy with Docker Compose on the VPS; put SQLite on the `shop-data`
  volume.
- [ ] Restrict the bot to the client's admins; verify a non-admin account
  cannot run `/admin`.
- [ ] Run one end-to-end test order: create, `/setstatus paid`, `/tracking`,
  buyer notification, `/export`.

## Day 2 — acceptance and handover

- [ ] Walk the client through `/start`, checkout, `/track`, `/admin`,
  `/orders`, `/tracking`, `/export`, `/stats` (15-minute call).
- [ ] Hand over: repository access, `.env` contents via a secret channel,
  deployment notes, database backup command:
  `docker compose exec bot python -c "import sqlite3; ..."` or simply copy
  the volume; better: `sqlite3 /data/shop.db ".backup /data/backup.db"`.
- [ ] Confirm the one included revision: collect a single consolidated list of
  changes, implement, redeploy.
- [ ] Ask for acceptance in LaborX and release the milestone.

## Scope guardrails

Included: catalog, cart/checkout, payment instructions, tracking, admin CRUD,
stock, CSV, deployment, one revision.

Not included (quote separately): card payments, automatic crypto payment
verification, WhatsApp channel, multi-language UI, delivery-provider API
integration, analytics dashboards, multi-admin roles, refunds automation.

## Reuse for future clients

- Change `SHOP_NAME`, `SHOP_CURRENCY`, `PAYMENT_METHODS` only for a basic shop.
- Add fields to `orders` + checkout states for niche stores (e.g. size/color).
- The service layer is tested independently, so client-specific changes stay
  small and verifiable.
- Estimated configuration-only delivery after the first build: 2–4 hours.

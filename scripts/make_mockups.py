"""Render the README screenshots from an HTML mock of the Telegram UI.

These are explicitly mockups: the bot is never connected to Telegram here. The
script exists so the screenshots can be regenerated after a UI change.

Requirements: chromium (or chromium-browser) on PATH.
Usage: python -m scripts.make_mockups
"""

from __future__ import annotations

import html
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs" / "screenshots"

CSS = """
* { box-sizing: border-box; }
body {
  margin: 0; padding: 26px 30px 14px; background: #d9e2ec;
  font-family: "DejaVu Sans", "Liberation Sans", Arial, sans-serif;
  display: flex; justify-content: center;
}
.phone {
  width: 420px; height: 880px; background: #0e1621; border-radius: 34px;
  box-shadow: 0 18px 45px rgba(16, 35, 55, .35); overflow: hidden;
  display: flex; flex-direction: column; border: 1px solid #0a1119;
}
.status { height: 26px; color: #cfd9e3; font-size: 11px; display: flex;
  justify-content: space-between; align-items: center; padding: 0 18px; }
.top { display: flex; align-items: center; gap: 10px; padding: 8px 14px 10px;
  background: #17212b; border-bottom: 1px solid #0b131c; }
.back { color: #6ab3f3; font-size: 20px; line-height: 1; }
.avatar { width: 34px; height: 34px; border-radius: 50%; background: #2f6f9f;
  color: #eaf4ff; font-size: 15px; display: flex; align-items: center;
  justify-content: center; font-weight: bold; }
.who { color: #f2f6fa; font-size: 14px; font-weight: bold; }
.sub { color: #7f93a6; font-size: 11px; }
.chat { flex: 1; padding: 12px 12px 6px; overflow: hidden; }
.msg { max-width: 84%; padding: 8px 11px; border-radius: 13px; margin: 0 0 7px;
  color: #e9eef4; font-size: 13px; line-height: 1.38; white-space: pre-wrap;
  word-wrap: break-word; }
.bot { background: #182533; border-bottom-left-radius: 4px; }
.user { background: #2b5278; margin-left: auto; border-bottom-right-radius: 4px; }
.name { color: #6ab3f3; font-weight: bold; }
.muted { color: #8fa3b5; }
.kb { display: flex; flex-direction: column; gap: 4px; margin: 2px 0 9px; }
.kb .row { display: flex; gap: 4px; }
.kb div.key {
  flex: 1; background: #1c2b3a; border-radius: 8px; color: #6ab3f3;
  font-size: 12px; padding: 8px 6px; text-align: center;
}
.photo { height: 148px; border-radius: 10px; margin-bottom: 8px;
  background: linear-gradient(135deg, #31475c, #4f8ba8);
  display: flex; align-items: center; justify-content: center;
  color: #eaf4ff; font-size: 46px; }
.doc { display: flex; gap: 9px; align-items: center; background: #182533;
  border-radius: 12px; padding: 9px 11px; margin-bottom: 8px; max-width: 84%; }
.doc .icon { width: 32px; height: 32px; border-radius: 50%; background: #2b5278;
  color: #fff; display: flex; align-items: center; justify-content: center;
  font-size: 14px; }
.doc .t { color: #6ab3f3; font-size: 12px; }
.doc .s { color: #8fa3b5; font-size: 10px; }
.input { background: #17212b; border-top: 1px solid #0b131c; padding: 8px 12px 14px;
  display: flex; gap: 8px; align-items: center; }
.field { flex: 1; color: #6d7f90; font-size: 12px; background: #0e1621;
  border-radius: 16px; padding: 9px 12px; }
.mic { width: 30px; height: 30px; border-radius: 50%; background: #2b5278; }
.footer { color: #5f7182; font-size: 10px; text-align: center; padding: 7px 0 12px; }
"""

LABEL_CSS = """
.label { position: fixed; left: 30px; right: 30px; bottom: 6px; text-align: center;
  line-height: 1.4;
  color: #64748b; font-size: 11px; letter-spacing: .02em; }
"""


def bubble(text: str, kind: str = "bot") -> str:
    return f'<div class="msg {kind}">{text}</div>'


def keyboard(rows: list[list[str]]) -> str:
    out = ['<div class="kb">']
    for row in rows:
        out.append('<div class="row">')
        out.extend(f'<div class="key">{html.escape(label)}</div>' for label in row)
        out.append("</div>")
    out.append("</div>")
    return "".join(out)


def screen(header: str, chat: str, label: str) -> str:
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>{CSS}{LABEL_CSS}</style></head>
<body>
  <div class="phone">
    <div class="status"><span>9:41</span><span>4G&nbsp;&nbsp;100%</span></div>
    <div class="top">
      <span class="back">&#8249;</span>
      <div class="avatar">NG</div>
      <div><div class="who">{header}</div><div class="sub">bot</div></div>
    </div>
    <div class="chat">{chat}</div>
    <div class="input"><div class="field">Message</div><div class="mic"></div></div>
    <div class="footer">Mockup — HTML rendering, not a real Telegram screenshot</div>
  </div>
  <div class="label">{label}</div>
</body></html>"""


SCREENS = {
    "01-catalog": screen(
        "Neo Gadgets",
        bubble(
            '<span class="name">Neo Gadgets</span>\n'
            "Browse the catalog, place an order and pay using the instructions "
            "shown after checkout."
        )
        + keyboard([["Catalog"], ["Track order", "My orders"], ["Help"]])
        + bubble("<b>Categories</b>\nChoose a category:")
        + keyboard([["Home & Office (2)"], ["Accessories (3)"], ["« Menu"]])
        + bubble("/shop", "user"),
        "Catalog: categories are inline buttons; every product shows live stock.",
    ),
    "02-product": screen(
        "Neo Gadgets",
        '<div class="photo">&#9749;</div>'
        + bubble(
            "<b>Smart Mug</b>\nKeeps coffee at 55 C for three hours.\n\n"
            "Price: <b>$24.50</b>\nIn stock: 12"
        )
        + keyboard([["Buy now"], ["« Back to category"]])
        + bubble("<b>Smart Mug</b>\nPrice: $24.50\n\nHow many would you like?")
        + keyboard([["1", "2", "3", "4", "5"], ["Cancel"]])
        + bubble("2", "user")
        + bubble("Added 2x Smart Mug.\n\n<b>Step 2 of 5</b> — send your full name.")
        + bubble("Ana Popescu", "user"),
        "Product card, quantity picker and the beginning of the checkout wizard.",
    ),
    "03-order-payment": screen(
        "Neo Gadgets",
        bubble(
            "<b>Review your order</b>\n\n"
            "2x Smart Mug — $49.00\n"
            "1x USB-C Cable — $9.99\n"
            "Total: <b>$58.99</b>\n\n"
            "Name: Ana Popescu\n"
            "Phone: +373 60 123 456\n"
            "Address: Str. Maria Cebotari 12, Chisinau\n"
            "Payment: USDT (TRC20)"
        )
        + keyboard([["Place order"], ["Cancel"]])
        + bubble("Place order", "user")
        + bubble(
            "<b>Order SB-000001 placed</b>\n"
            "Total: <b>$58.99</b>\n\n"
            "<b>Payment — USDT (TRC20)</b>\n"
            "Send the exact amount in USDT (TRC20) to TXYZ...DEMO\n"
            "Then send the transaction hash in this chat.\n\n"
            "Keep your order number: <b>SB-000001</b>"
        ),
        "The order is recorded and payment instructions come from PAYMENT_METHODS. "
        "No card processor, no custody.",
    ),
    "04-tracking": screen(
        "Neo Gadgets",
        bubble("/track SB-000001", "user")
        + bubble(
            "<b>Order SB-000001</b>\n"
            "Status: Shipped\n\n"
            "<b>Items</b>\n"
            "2x Smart Mug — $49.00\n"
            "1x USB-C Cable — $9.99\n\n"
            "<b>Total:</b> $58.99\n"
            "<b>Payment:</b> USDT (TRC20)\n"
            "<b>Name:</b> Ana Popescu\n"
            "<b>Phone:</b> +373 60 123 456\n"
            "<b>Address:</b> Str. Maria Cebotari 12, Chisinau\n"
            "<b>Tracking:</b> TRACK-2026-0042\n\n"
            "<b>History</b>\n"
            "2026-11-20 19:58 — New\n"
            "2026-11-20 20:03 — Paid\n"
            "2026-11-20 20:04 — Shipped"
        ),
        "A buyer sees only their own orders; the status change came from /tracking.",
    ),
    "05-admin": screen(
        "Neo Gadgets Admin",
        bubble("/orders", "user")
        + bubble(
            "<b>Orders</b>\n\n"
            "SB-000003 · $24.50 · New · Ana Popescu\n"
            "SB-000002 · $19.98 · Paid · Ion Rusu\n"
            "SB-000001 · $58.99 · Shipped · Ana Popescu"
        )
        + bubble("/tracking SB-000002 TRACK-2026-0044", "user")
        + bubble("Tracking set for SB-000002. Buyer notified.")
        + '<div class="doc"><div class="icon">CSV</div><div>'
        '<div class="t">orders-20261120-2015.csv</div>'
        '<div class="s">CSV · 3 orders · 1.9 KB</div></div></div>'
        + bubble("/stats", "user")
        + bubble(
            "<b>Shop stats</b>\n"
            "Active products: 5\n"
            "Revenue (paid+): $78.97\n"
            "Orders: new: 1, paid: 1, shipped: 1\n"
            "Low stock: Power Bank (3)"
        ),
        "Admin: order list, tracking notification to the buyer, CSV export and stats.",
    ),
}


def main() -> None:
    chromium = shutil.which("chromium") or shutil.which("chromium-browser")
    if not chromium:
        raise SystemExit("chromium is required to render the mockups")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        for name, markup in SCREENS.items():
            page = Path(directory) / f"{name}.html"
            page.write_text(markup, encoding="utf-8")
            subprocess.run(
                [
                    chromium,
                    "--headless",
                    "--no-sandbox",
                    "--disable-gpu",
                    "--hide-scrollbars",
                    "--force-device-scale-factor=2",
                    "--window-size=480,980",
                    f"--screenshot={OUT_DIR / f'{name}.png'}",
                    page.as_uri(),
                ],
                check=True,
                capture_output=True,
            )
            print(f"wrote {OUT_DIR / f'{name}.png'}")


if __name__ == "__main__":
    main()

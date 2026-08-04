#!/usr/bin/env python3
"""Build shopping-cart emails from cart JSON files.

Every subtotal and total is computed here, never hand-written — in the first run of this
workflow, three of four hand-written totals were arithmetically wrong.

Usage:
    python3 build_emails.py carts/*.json [--out-dir out] [--template path]

Schema: ../references/cart-schema.md
"""
from __future__ import annotations

import argparse
import html as H
import json
import pathlib
import re
import sys

GREEN = "#1f3a34"
MUTED = "#7a7268"
RULE = "#ece7e0"
DEFAULT_EYEBROW = "Shopping Cart"
DEFAULT_FOOTER = "Tap any item name to open it on the retailer's site."


def money(amount: float, cur: str = "$") -> str:
    return f"{cur}{amount:,.2f}"


def sizebox(rows) -> str:
    if not rows:
        return ""
    cells = "".join(
        f'<tr><td style="padding:2px 0;color:{MUTED};font-size:12px;letter-spacing:1.4px;'
        f'text-transform:uppercase;font-weight:600;width:118px;vertical-align:top;">{H.escape(str(label))}</td>'
        f'<td style="padding:2px 0;color:#3d3833;font-size:14px;line-height:1.55;">{value}</td></tr>'
        for label, value in rows
    )
    return (
        '<tr><td style="padding:18px 30px 4px;">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="background:#f6f4f0;border-radius:10px;border-left:3px solid {GREEN};">'
        '<tr><td style="padding:14px 18px;">'
        f'<table role="presentation" cellpadding="0" cellspacing="0" width="100%">{cells}</table>'
        "</td></tr></table></td></tr>"
    )


def note(text: str, kind: str = "info") -> str:
    bg, bar = ("#fdf6e8", "#c8963e") if kind == "warn" else ("#f2f6f5", "#4d7c6f")
    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="background:{bg};border-radius:9px;border-left:3px solid {bar};margin:6px 0 16px;">'
        f'<tr><td style="padding:13px 16px;color:#4a443d;font-size:13px;line-height:1.65;">{text}</td>'
        "</tr></table>"
    )


def heading(title: str, blurb: str = "") -> str:
    out = [
        f'<div style="margin:22px 0 0;"><div style="color:{GREEN};font-size:16px;'
        f'font-weight:700;letter-spacing:-.2px;">{title}</div>'
    ]
    if blurb:
        out.append(
            f'<div style="color:{MUTED};font-size:13px;line-height:1.65;margin:6px 0 4px;">{blurb}</div>'
        )
    out.append("</div>")
    return "".join(out)


def section(sec: dict, cur: str) -> tuple[str, float]:
    """Render one item section. Returns (html, subtotal)."""
    html = [heading(sec["title"], sec.get("blurb", ""))]
    subtotal = 0.0
    rows = []

    for item in sec.get("items", []):
        qty = int(item.get("qty", 1) or 1)
        price = item.get("price")
        if price is None:
            raise ValueError(f"item {item.get('name')!r} has no price")
        if isinstance(price, str):
            raise ValueError(
                f"item {item.get('name')!r} price must be a number, got the string {price!r}"
            )
        subtotal += qty * float(price)

        badge = (
            f'<span style="display:inline-block;background:{GREEN};color:#fff;font-size:11px;'
            f'font-weight:700;padding:2px 7px;border-radius:20px;margin-right:7px;">&times;{qty}</span>'
            if qty > 1
            else ""
        )
        name = H.escape(item["name"])
        label = (
            f'<a href="{H.escape(item["url"], quote=True)}" style="color:{GREEN};font-weight:600;'
            f'text-decoration:none;border-bottom:1px solid #c3d5cf;">{name}</a>'
            if item.get("url")
            else f'<span style="color:{GREEN};font-weight:600;">{name}</span>'
        )
        meta = (
            f'<div style="color:{MUTED};font-size:12px;line-height:1.5;margin-top:3px;">{item["meta"]}</div>'
            if item.get("meta")
            else ""
        )
        shown = money(float(price), cur) + (" ea" if qty > 1 else "")
        rows.append(
            f'<tr><td style="padding:11px 0;border-top:1px solid {RULE};font-size:14px;'
            f'line-height:1.5;">{badge}{label}{meta}</td>'
            f'<td align="right" style="padding:11px 0 11px 12px;border-top:1px solid {RULE};'
            f'white-space:nowrap;vertical-align:top;color:#3d3833;font-size:14px;font-weight:700;">'
            f"{shown}</td></tr>"
        )

    if rows:
        rows.append(
            f'<tr><td style="padding:9px 0 0;border-top:2px solid {GREEN};color:{MUTED};'
            f'font-size:12px;letter-spacing:1.2px;text-transform:uppercase;font-weight:600;">Subtotal</td>'
            f'<td align="right" style="padding:9px 0 0 12px;border-top:2px solid {GREEN};'
            f'color:{GREEN};font-size:15px;font-weight:700;white-space:nowrap;">'
            f"{money(subtotal, cur)}</td></tr>"
        )
        html.append(
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'style="margin:8px 0 4px;">{"".join(rows)}</table>'
        )
    return "".join(html), subtotal


def build(cart: dict, template: str) -> tuple[str, float, int]:
    cur = cart.get("currency", "$")
    chunks: list[str] = []
    total = 0.0
    items = 0

    for sec in cart.get("sections", []):
        kind = sec.get("type", "section")
        if kind == "note":
            chunks.append(note(sec["text"], sec.get("kind", "info")))
        elif kind == "prose":
            chunks.append(heading(sec["title"], sec.get("blurb", "")))
            if sec.get("body"):
                chunks.append(
                    f'<div style="color:#4a443d;font-size:13px;line-height:1.75;margin:4px 0 8px;">'
                    f'{sec["body"]}</div>'
                )
        elif kind == "section":
            body, subtotal = section(sec, cur)
            chunks.append(body)
            total += subtotal
            items += sum(int(i.get("qty", 1) or 1) for i in sec.get("items", []))
        else:
            raise ValueError(f"unknown section type {kind!r}")

    values = {
        "EYEBROW": cart.get("eyebrow", DEFAULT_EYEBROW),
        "NAME": H.escape(cart["name"]),
        "SUBTITLE": cart.get("subtitle", ""),
        "SIZEBOX": sizebox(cart.get("sizebox")),
        "SECTIONS": "".join(chunks),
        "TOTAL": money(total, cur),
        "FOOTNOTE": cart.get("footnote", ""),
        "FOOTER": cart.get("footer", DEFAULT_FOOTER),
    }

    # Single pass, so substituted content is never itself rescanned for placeholders.
    # (A template that merely *documents* "{{SECTIONS}}" in a comment would otherwise get
    # a second, hidden copy of the whole body injected there.)
    missing: list[str] = []

    def sub(m: "re.Match[str]") -> str:
        key = m.group(1)
        if key not in values:
            missing.append(key)
            return m.group(0)
        return values[key]

    html = re.sub(r"\{\{(\w+)\}\}", sub, template)
    if missing:
        raise ValueError(f"template has unknown placeholder(s): {', '.join(sorted(set(missing)))}")
    return html, total, items


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("carts", nargs="+", help="cart JSON files")
    ap.add_argument("--out-dir", default="out")
    ap.add_argument("--template", help="defaults to ../assets/email-template.html")
    args = ap.parse_args()

    here = pathlib.Path(__file__).resolve().parent
    tpl_path = pathlib.Path(args.template) if args.template else here.parent / "assets" / "email-template.html"
    template = tpl_path.read_text()

    out_dir = pathlib.Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    grand = 0.0
    failures = []

    for path in args.carts:
        cart = json.loads(pathlib.Path(path).read_text())
        html, total, items = build(cart, template)

        expected = cart.get("expect_total")
        flag = ""
        if expected is not None and abs(float(expected) - total) > 0.01:
            flag = f"  ** MISMATCH: expected {money(float(expected))} **"
            failures.append((cart["slug"], expected, total))

        if "{{" in html:
            failures.append((cart["slug"], "unfilled placeholder", None))
            flag += "  ** UNFILLED PLACEHOLDER **"

        dest = out_dir / f"email-{cart['slug']}.html"
        dest.write_text(html)
        grand += total
        print(f"{dest}  {items:>3} items  {money(total, cart.get('currency', '$')):>12}{flag}")

    print(f"{'GRAND TOTAL':>40}  {money(grand)}")

    if failures:
        print("\nFAILED:", file=sys.stderr)
        for slug, exp, got in failures:
            print(f"  {slug}: expected {exp}, computed {got}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

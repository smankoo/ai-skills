#!/usr/bin/env python3
"""Search Sumeet's Amazon.ca order history from the iMac's real Chrome, human-style.

Usage: ~/.hermes/tools-venv/bin/python amazon_order_search.py "kids shoes" ["sneakers" ...] [--details]
Prints JSON lines: {query, date, title, asin, order_id}. With --details it also opens each order's details
page and adds price/size text. Needs the tunnel: ssh -fN -L 19334:127.0.0.1:9335 sumeet@100.119.136.41 (iMac Chrome moved to 9335 on 2026-10-20)

Why: before ANY purchase research, check what we already bought (sizes, brands, what worked). Amazon flags the
VPS Chrome as an AI agent, so this always runs through the iMac's Chrome with human-like input (human_cdp.Tab).
"""
import json, re, subprocess, sys, time, random, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from human_cdp import Tab

EP = "http://127.0.0.1:19334"
# iMac Chrome CDP port. 9334 was taken by Sumeet's open-browser-control bridge-server on 2026-10-18;
# Magnus relaunched the persistent Chrome on 9335.
IMAC_PORT = os.environ.get("IMAC_CDP_PORT", "9335")


def ensure_tunnel():
    if subprocess.run("ss -ltn | grep -q ':19334 '", shell=True).returncode != 0:
        subprocess.run(["ssh", "-fN", "-o", "ExitOnForwardFailure=yes", "-L", f"19334:127.0.0.1:{IMAC_PORT}",
                        "sumeet@100.119.136.41"], check=True, timeout=30)
        time.sleep(1)


EXTRACT = r"""(() => {
  const out = [];
  document.querySelectorAll('.order-card, .js-order-card, [class*="order-card"], .a-box-group').forEach(card => {
    const txt = card.innerText || '';
    const date = (txt.match(/Ordered on ([A-Z][a-z]+ \d{1,2}, \d{4})/) || txt.match(/ORDER PLACED\s+([A-Z][a-z]+ \d{1,2}, \d{4})/) || [])[1] || '';
    const oid = (txt.match(/\b(\d{3}-\d{7}-\d{7})\b/) || [])[1] || ((card.querySelector('a[href*="orderID="]')||{}).href||'').replace(/.*orderID=([\d-]+).*/, '$1');
    card.querySelectorAll('a[href*="/dp/"], a[href*="/gp/product/"]').forEach(a => {
      const t = a.innerText.trim(); if (t.length < 8) return;
      const asin = (a.href.match(/\/(?:dp|gp\/product)\/([A-Z0-9]{10})/) || [])[1] || '';
      out.push({date, title: t.slice(0, 200), asin, order_id: oid});
    });
  });
  if (!out.length) {  // search-results layout: "View order details" blocks
    const t = document.body.innerText;
    const re = /Ordered on ([A-Z][a-z]+ \d{1,2}, \d{4})\n+([^\n]{8,220})/g; let m;
    while ((m = re.exec(t))) out.push({date: m[1], title: m[2].trim(), asin: '', order_id: ''});
    const links = [...document.querySelectorAll('a[href*="orderID="]')].map(a => a.href.replace(/.*orderID=([\d-]+).*/, '$1'));
    const asins = [...document.querySelectorAll('a[href*="/dp/"]')].filter(a => a.innerText.trim().length > 8).map(a => (a.href.match(/\/dp\/([A-Z0-9]{10})/) || [])[1]);
    out.forEach((o, i) => { o.order_id = links[i] || ''; o.asin = asins[i] || ''; });
  }
  return JSON.stringify(out);
})()"""


def search(t, q):
    # Human path: focus the orders search box and type, like a person would.
    t.navigate("https://www.amazon.ca/gp/css/order-history")
    t.wait_load(); time.sleep(random.uniform(1.5, 3))
    if t.js("!!document.querySelector('#searchOrdersInput')"):
        t.type_sel("#searchOrdersInput", q); t.pause(0.3, 0.8); t.enter()
    else:
        t.navigate("https://www.amazon.ca/your-orders/search?search=" + q.replace(" ", "+"))
    t.wait_load(); time.sleep(random.uniform(2, 3.5))
    if re.search(r"unauthorized AI agent", t.text(3000), re.I):
        raise SystemExit("AMAZON AI-AGENT NOTICE on the iMac too, stopping")
    # Blind is not "no orders": a signed-out profile lands on /ap/signin and used to print nothing (2026-10-20).
    if "/ap/signin" in (t.url() or "") or re.search(r"^Sign in", t.text(200).strip()):
        raise SystemExit("SIGNED OUT of Amazon.ca in the iMac Chrome profile: sign in first (1Password item 'amazon.ca'); "
                         "no results is NOT the same as no orders")
    t.wheel(500); t.pause(0.5, 1.2)
    return json.loads(t.js(EXTRACT) or "[]")


def details(t, oid):
    t.navigate(f"https://www.amazon.ca/your-orders/order-details?orderID={oid}")
    t.wait_load(); time.sleep(random.uniform(1.5, 3))
    txt = t.text(12000)
    total = (re.search(r"Grand Total:\s*\$([\d.,]+)", txt) or [None, ""])[1]
    sizes = sorted(set(re.findall(r"Size:\s*([^\n]{1,40})", txt)))
    colours = sorted(set(re.findall(r"Colou?r:\s*([^\n]{1,40})", txt)))
    return {"grand_total": total, "sizes": sizes, "colours": colours}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    want_details = "--details" in sys.argv
    ensure_tunnel()
    t = Tab.new(EP, "https://www.amazon.ca/")
    try:
        seen = set()
        for q in args:
            for o in search(t, q):
                key = (o["order_id"], o["title"][:60])
                if key in seen:
                    continue
                seen.add(key)
                if want_details and o["order_id"]:
                    o.update(details(t, o["order_id"]))
                o["query"] = q
                print(json.dumps(o, ensure_ascii=False), flush=True)
            time.sleep(random.uniform(3, 6))
    finally:
        t.close()


if __name__ == "__main__":
    main()

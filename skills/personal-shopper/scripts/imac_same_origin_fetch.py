#!/usr/bin/env python3
"""imac_same_origin_fetch.py: same-origin fetch() inside the iMac's real Chrome, for stores whose JSON
endpoints (Shopify products.json, WooCommerce Store API) block the VPS IP.

Usage: ~/.hermes/tools-venv/bin/python imac_same_origin_fetch.py https://www.kamik.com/ "/collections/x/products.json?limit=60" [...]
Prints "<status>\n<body>" per path. Needs the tunnel 127.0.0.1:19334 -> iMac Chrome CDP (see browser-ops).
"""
import json, os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "browser-ops", "scripts"))
from human_cdp import Tab

def main():
    origin, paths = sys.argv[1], sys.argv[2:]
    t = Tab.new(os.environ.get("CDP", "http://127.0.0.1:19334"), "about:blank")
    try:
        t.cdp("Page.navigate", url=origin)
        time.sleep(10)
        for p in paths:
            print(t.js(f"(async () => {{ const r = await fetch({json.dumps(p)}); return r.status + '\\n' + (await r.text()); }})()"))
    finally:
        t.close()

if __name__ == "__main__":
    main()

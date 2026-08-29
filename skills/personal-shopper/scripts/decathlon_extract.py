#!/usr/bin/env python3
"""Decathlon.ca product extractor — CDP windowed Chrome on the Mac (rung 3).

WHY CDP: the VPS is HARD Cloudflare-walled ("Just a moment..." 403) on every
transport — curl, requests, and all API guesses. `web_extract` (Crawl4AI) DOES
render the PDP shell (name, brand, visible price, star rating, ID) but the
critical fibre COMPOSITION lives inside a *collapsed* "Specifications" accordion
that web_extract never expands, and it returns no image URL / per-size stock.
So web_extract is only a partial first pass; the real recipe is Mac CDP, which
can click the accordion open and read the spec table.

HOW TO RUN (all on the Mac over Tailscale ssh sumeet@100.116.71.40):
  1. Launch a throwaway debug Chrome (NOT headless — headless UA gets flagged):
     nohup "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
       --remote-debugging-port=9333 "--remote-allow-origins=*" \
       --user-data-dir=/tmp/scrape-profile --no-first-run \
       --no-default-browser-check --window-size=1400,1000 \
       >/tmp/scrape-chrome.log 2>&1 &
     (quote --remote-allow-origins=* or zsh globs it; Chrome v151+ needs PUT on /json/new)
  2. python3 -m venv /tmp/scrape-venv && /tmp/scrape-venv/bin/pip install websocket-client
  3. base64-ship this file to /tmp/dec_cdp.py, then:
     /tmp/scrape-venv/bin/python /tmp/dec_cdp.py <pdp_url> [<pdp_url> ...]
  4. Cleanup: pkill -f "remote-debugging-port=9333"; rm -rf /tmp/scrape-profile /tmp/scrape-venv

OUTPUT per URL: {name, brand, image, rating, visible_price, offers[],
  composition_hits[] (e.g. "100.0% Cotton","97.0% Cotton","3.0% Elastane"),
  specs{} (Main Material, Cut, Collar Type, Skill Level, ... + env-impact %s)}.

NATURAL-FIBRE GATE: sum the natural fibres from composition_hits (cotton, wool,
linen, silk, cashmere, lyocell/Tencel). Verified 2026-08-29 on two live PDPs:
  Fitness T-Shirt Essentials 500 (Domyos)  -> "100.0% Cotton" main body -> PASS
  Cotton Sweatshirt 500 Essentiel (Domyos) -> "41.0% Cotton, 59.0% Polyester" -> FAIL 70%
  (Note Decathlon's "Cotton Sweatshirt"/"Main Material: Polyester" names lie about
   the blend — always read the %; the mostly-synthetic athleisure is the trap.)

Product URL shape: https://www.decathlon.ca/en/p/<slug>/<modelId>/c...m<productId>
  (also .../en/p/<productId>/<slug> works). Discover via web_search "site:decathlon.ca ...".
Images: contents.mediadecathlon.com/.../picture.jpg?format=auto&f=650x0 — NOT
  walled, returns image/jpeg from the VPS directly (verify bytes before emailing).
"""
import json, sys, time, urllib.request, websocket

CDP = "http://127.0.0.1:9333"

def new_tab():
    req = urllib.request.Request(CDP + "/json/new?about:blank", method="PUT")
    return json.load(urllib.request.urlopen(req))["webSocketDebuggerUrl"]

JS_EXPAND = r"""
(() => {
  document.querySelectorAll('button,summary,[role=button]').forEach(b => {
    const t = (b.textContent||'').trim().toLowerCase();
    if (/specification|description|composition|material|usage|feature/.test(t)) {
      try { b.click(); } catch(e){}
    }
  });
  return true;
})()
"""

EXTRACT = r"""
(() => {
  const out = {};
  const lds = [...document.querySelectorAll('script[type="application/ld+json"]')]
    .map(s => { try { return JSON.parse(s.textContent); } catch(e){ return null; } }).filter(Boolean);
  const flat = [];
  lds.forEach(j => Array.isArray(j) ? flat.push(...j) : (j['@graph']?flat.push(...j['@graph']):flat.push(j)));
  const prod = flat.find(j => (j['@type']||'').toString().includes('Product'));
  if (prod) {
    out.name = prod.name;
    out.brand = prod.brand && (prod.brand.name || prod.brand);
    out.image = Array.isArray(prod.image)?prod.image[0]:prod.image;
    out.sku = prod.sku || prod.mpn;
    const offs = Array.isArray(prod.offers)?prod.offers:[prod.offers].filter(Boolean);
    out.offers = offs.map(o => ({price:o.price, cur:o.priceCurrency,
      avail:String(o.availability||'').replace(/https?:\/\/schema.org\//,'')}));
    out.rating = prod.aggregateRating && prod.aggregateRating.ratingValue;
  }
  if (!out.image) out.image = (document.querySelector('meta[property="og:image"]')||{}).content;
  if (!out.image) {
    const im = [...document.querySelectorAll('img')].map(x=>x.currentSrc||x.src)
      .find(u=>/contents\.mediadecathlon\.com/i.test(u));
    if (im) out.image = im.replace(/f=\d+x\d+/, 'f=650x0');
  }
  const pm = document.body.innerText.match(/\$\d+\.\d{2}/);
  out.visible_price = pm && pm[0];
  const body = document.body.innerText;
  const compRe = /(\d{1,3}(?:\.\d+)?\s?%)\s*(cotton|polyester|elastane|wool|linen|nylon|viscose|spandex|acrylic|silk|lyocell|polyamide|modal|recycled polyester)/gi;
  const comps = [...body.matchAll(compRe)].map(m => (m[1]+' '+m[2]).replace(/\s+/g,' ').trim());
  out.composition_hits = [...new Set(comps)].slice(0,10);
  const specs = {};
  document.querySelectorAll('dl').forEach(dl => {
    const dts = dl.querySelectorAll('dt'), dds = dl.querySelectorAll('dd');
    for (let i=0;i<dts.length;i++){ specs[dts[i].innerText.trim()] = (dds[i]||{}).innerText; }
  });
  document.querySelectorAll('table tr').forEach(tr => {
    const c = tr.querySelectorAll('th,td');
    if (c.length===2) specs[c[0].innerText.trim()] = c[1].innerText.trim();
  });
  out.specs = specs;
  return out;
})()
"""

def run(url):
    ws = websocket.create_connection(new_tab(), max_size=None)
    mid = [0]
    def cmd(method, params=None):
        mid[0]+=1; i=mid[0]
        ws.send(json.dumps({"id":i,"method":method,"params":params or {}}))
        while True:
            m=json.loads(ws.recv())
            if m.get("id")==i: return m.get("result",{})
    cmd("Page.enable"); cmd("Runtime.enable")
    cmd("Page.navigate", {"url":url})
    time.sleep(13)                       # render + let Cloudflare pass
    cmd("Runtime.evaluate", {"expression":JS_EXPAND})
    time.sleep(2.5)                      # accordions open
    r = cmd("Runtime.evaluate", {"expression":EXTRACT, "returnByValue":True})
    ws.close()
    return r.get("result",{}).get("value")

if __name__ == "__main__":
    res=[]
    for u in sys.argv[1:]:
        try: res.append({"url":u, "data":run(u)})
        except Exception as e: res.append({"url":u,"error":str(e)})
    print(json.dumps(res, indent=2))

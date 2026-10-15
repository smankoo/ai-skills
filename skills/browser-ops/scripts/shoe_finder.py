#!/usr/bin/env python3
"""shoe_finder.py: live in-stock check for a size + width on picky shoe stores, using the iMac's
real windowed Chrome (home IP, macOS UA, Cloudflare-cleared profile) and human-like input.

Run ON the iMac (CDP 127.0.0.1:9334) or from the VPS through `ssh -L 19334:127.0.0.1:9334`:
  shoe_finder.py --store naturalizer --size 6 --width wide [--query "pump"] [--max 8] [--cdp URL]
  shoe_finder.py --store clarks --size 6 --width wide --query "loafer"
Prints a JSON list: [{name, price, was, url, image, size, width, in_stock, evidence}] for items CONFIRMED
in stock on the product page (not just by a listing filter). Finishes in about 1-3 minutes.

How each store works (verified 2026-10-15):
  naturalizer.ca: Cloudflare challenge clears in a FOREGROUND tab within ~3 s. Listing = Coveo headless
    results; the URL hash takes f-productsize=6.0&f-productwidth=Wide. On the product page, each
    `.VariantTile` has aria-label "Size 6.0 out of stock" / "Shoe width Wide"; picking the width
    re-renders the size tiles for that width.
  clarks.com/en-ca: Next.js. PDP sizes are buttons with aria-label/text; width tiles (Standard/Wide).
Pitfalls: keep the tab in front (Page.bringToFront) or the challenge never clears; Network.enable
during a challenge can stall it; space PDP loads 2-4 s apart.
"""
import argparse, json, os, re, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from human_cdp import Tab

def wait_clear(t, secs=40):
    t.cdp("Page.bringToFront")
    end = time.time() + secs
    i = 0
    while time.time() < end:
        title = (t.js("document.title") or "").lower()
        if "just a moment" not in title and "verification" not in (t.text(300) or "").lower():
            return True
        i += 1
        t.move(300 + (i * 37) % 500, 250 + (i * 23) % 300)
        time.sleep(2.5)
    return False

def goto(t, url, settle=3.0):
    t.cdp("Page.navigate", url=url)
    time.sleep(1.5)
    ok = wait_clear(t)
    t.wait_load(settle=(settle, settle + 1.5))
    return ok

TILE_JS = r"""(() => { const out=[], seen=new Set();
 const prices=[...document.querySelectorAll('*')].filter(e=>e.children.length===0 && /^(Current price|Sale price|Price)$/i.test(e.textContent.trim()));
 for (const p of prices) { let c=p; for(let i=0;i<8 && c;i++){ c=c.parentElement; if(c && c.querySelector('a[href]') && c.querySelector('img')) break; }
   if(!c) continue; const a=c.querySelector('a[href*="/product/"],a[href*="/p/"],a[href]'); const h=a.href.split('?')[0]; if(seen.has(h)) continue; seen.add(h);
   const txt=c.innerText.replace(/\s+/g,' ').trim(); const m=[...txt.matchAll(/\$\s?([\d,]+\.\d{2})/g)].map(x=>parseFloat(x[1].replace(',','')));
   const name=(c.querySelector('h2,h3,[class*=name i],[class*=title i]')||{}).innerText||txt.replace(/Current price.*$/,'').replace(/^.*NEW & NOW/,'');
   out.push({url:h, name:name.trim().slice(0,90), price:m[0]||null, was:m[1]||null, image:(c.querySelector('img')||{}).src||''}); }
 return JSON.stringify(out); })()"""

def naturalizer(t, a):
    width = {"wide": "Wide", "medium": "Medium", "narrow": "Narrow", "extra wide": "Extra Wide"}[a.width.lower()]
    size = f"{float(a.size):.1f}"
    base = "https://www.naturalizer.ca/en/browse/shoes/womens"
    if a.query:
        base = "https://www.naturalizer.ca/en/search?q=" + re.sub(r"\s+", "+", a.query.strip())
    url = f"{base}#sortCriteria=relevance&f-productsize={size}&f-productwidth={width}"
    if not goto(t, "https://www.naturalizer.ca/"):
        return [], "blocked at home page"
    goto(t, url, settle=4)
    tiles = json.loads(t.js(TILE_JS) or "[]")
    total = re.search(r"of ([\d,]+) products", t.text(5000) or "")
    out = []
    for tile in tiles[: a.max * 2]:
        if len(out) >= a.max:
            break
        goto(t, tile["url"])
        # pick the width tile first (re-renders sizes), human click
        wsel = f"[...document.querySelectorAll('.VariantTile--SizeWidth')].find(e=>/^\\s*{width}\\s*$/i.test(e.innerText))"
        if t.js(f"!!({wsel})") and not t.js(f"({wsel}).className.includes('active')"):
            try:
                t.click(wsel); time.sleep(1.5)
            except Exception:
                pass
        info = json.loads(t.js("""JSON.stringify({
          w:[...document.querySelectorAll('.VariantTile--SizeWidth')].map(e=>e.getAttribute('aria-label')||''),
          s:[...document.querySelectorAll('.VariantTile:not(.VariantTile--SizeWidth)')].map(e=>e.getAttribute('aria-label')||'')})""") or "{}")
        lab = next((x for x in info.get("s", []) if re.match(rf"Size {re.escape(size)}\b", x)), None)
        wl = next((x for x in info.get("w", []) if width.lower() in x.lower()), None)
        ok = bool(lab and "out of stock" not in lab.lower() and wl and "out of stock" not in wl.lower())
        tile.update(size=a.size, width=width, in_stock=ok, evidence=f"{wl} / {lab}")
        if ok:
            out.append(tile)
        time.sleep(1.5)
    return out, f"listing total (store filter {size} {width}): {total.group(1) if total else '?'}"

def clarks(t, a):
    """clarks.com/en-ca: search links look like /en-ca/<slug>/<sku>-p. Every PDP embeds __NEXT_DATA__ with
    variants[{size, fitLabel (Medium/Wide/...), stock{status, availableQuantity}, price[{actualPrice, wasPrice}]}]."""
    q = (a.query + " womens").strip()
    goto(t, "https://www.clarks.com/en-ca")
    goto(t, "https://www.clarks.com/en-ca/search?q=" + re.sub(r"\s+", "+", q), settle=4)
    links = json.loads(t.js(r"""JSON.stringify([...new Set([...document.querySelectorAll('a[href]')].map(a=>a.href.split('?')[0]).filter(h=>/\/en-ca\/[^/]+\/\d{6,}-p$/.test(h) && !/egift/.test(h)))].slice(0,40))""") or "[]")
    want_w = {"wide": "wide", "medium": "medium", "standard": "medium", "extra wide": "extra wide", "narrow": "narrow"}[a.width.lower()]
    sz = str(a.size).rstrip("0").rstrip(".") if "." in str(a.size) else str(a.size)
    out = []
    for u in links[: a.max * 3]:
        if len(out) >= a.max:
            break
        goto(t, u, settle=2)
        d = json.loads(t.js(r"""(() => { const s=document.getElementById('__NEXT_DATA__'); if(!s) return 'null';
          const txt=s.textContent; const i=txt.indexOf('"variants":['); if(i<0) return 'null';
          let depth=0, j=i+11; for(; j<txt.length; j++){ const c=txt[j]; if(c==='[') depth++; else if(c===']'){ depth--; if(depth===0) break; } }
          let v; try { v=JSON.parse(txt.slice(i+11, j+1)); } catch(e) { return 'null'; }
          return JSON.stringify({name:(document.querySelector('h1')||{}).innerText||document.title,
            img:(document.querySelector('meta[property="og:image"]')||{}).content||'',
            v:v.map(x=>({size:x.size, fit:x.fitLabel, st:(x.stock||{}).status, q:(x.stock||{}).availableQuantity,
                         p:((x.price||[])[0]||{}).actualPrice, w:((x.price||[])[0]||{}).wasPrice}))}); })()""") or "null")
        if not d:
            continue
        hit = next((x for x in d["v"] if str(x["size"]) == sz and (x["fit"] or "").lower() == want_w and x["st"] == "inStock"), None)
        if hit:
            cents = lambda m: (m or {}).get("centAmount", 0) / 100 if m else None
            out.append(dict(url=u, name=d["name"].strip()[:90], price=cents(hit["p"]), was=cents(hit["w"]) if hit["w"] and hit["w"] != hit["p"] else None,
                            image=d["img"], size=a.size, width=hit["fit"], in_stock=True, evidence=f"variant {sz} {hit['fit']} inStock qty {hit['q']}"))
        time.sleep(1.2)
    return out, f"checked {min(len(links), a.max * 3)} of {len(links)} search results"

def anyurl(t, a):
    """Any product page (--url): read schema.org Product offers (JSON-LD) for size/width availability.
    Works on most big retailers (Ecco, Sorel, Hudson's Bay, Nordstrom, SoftMoc...). Best effort: if the page
    doesn't list per-size offers, it says so instead of guessing."""
    goto(t, a.url, settle=3)
    d = json.loads(t.js(r"""(() => { const items=[];
      const walk=o=>{ if(!o||typeof o!=='object') return; if(Array.isArray(o)) return o.forEach(walk);
        if(/Product/.test(o['@type'])) items.push(o); Object.values(o).forEach(v=>{ if(v&&typeof v==='object') walk(v); }); };
      document.querySelectorAll('script[type="application/ld+json"]').forEach(s=>{ try{ walk(JSON.parse(s.textContent)); }catch(e){} });
      return JSON.stringify({title:document.title, items:items.slice(0,80).map(p=>({name:p.name, size:p.size, sku:p.sku,
        offers:[].concat(p.offers||[]).flatMap(o=>o.offers?[].concat(o.offers):[o]).map(o=>({price:o.price, cur:o.priceCurrency, av:o.availability, name:o.name, sku:o.sku, url:o.url}))}))}); })()""") or "{}")
    sz = str(a.size); w = a.width.lower()
    out = []
    for it in d.get("items", []):
        for o in it.get("offers", []):
            label = " ".join(str(x) for x in (it.get("name"), it.get("size"), o.get("name"), o.get("sku")) if x)
            if re.search(rf"(^|[^\d.]){re.escape(sz)}([^\d]|$)", label) and (w in ("medium", "any") or w in label.lower() or (w == "wide" and re.search(r"\bW\b|\bWW\b|wide", label))):
                if "InStock" in str(o.get("av")):
                    out.append(dict(url=o.get("url") or a.url, name=(it.get("name") or d.get("title", ""))[:90], price=float(o["price"]) if o.get("price") else None,
                                    was=None, image="", size=a.size, width=a.width, in_stock=True, evidence=f"JSON-LD offer '{label[:80]}' {o.get('av')} {o.get('cur')}"))
    note = f"{len(d.get('items', []))} JSON-LD products on page"
    if not out:
        note += " — no per-size in-stock offer found; open the page in the real browser and read the size picker"
    return out, note

STORES = {"naturalizer": naturalizer, "clarks": clarks, "url": anyurl}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", required=True, choices=sorted(STORES))
    ap.add_argument("--size", required=True)
    ap.add_argument("--width", default="medium")
    ap.add_argument("--query", default="")
    ap.add_argument("--url", default="")
    ap.add_argument("--max", type=int, default=6)
    ap.add_argument("--cdp", default=os.environ.get("SHOE_CDP", "http://127.0.0.1:9334"))
    a = ap.parse_args()
    t0 = time.time()
    t = Tab.new(a.cdp, "about:blank")
    try:
        res, note = STORES[a.store](t, a)
    finally:
        t.close()
    print(json.dumps({"store": a.store, "size": a.size, "width": a.width, "query": a.query, "note": note,
                      "seconds": round(time.time() - t0), "in_stock": res}, indent=1))

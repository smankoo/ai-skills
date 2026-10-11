#!/usr/bin/env python3
"""
walmart_extract.py — extract product data from walmart.ca (George, etc.)

Walmart.ca is walled by PerimeterX from the VPS on EVERY transport (curl -> /blocked
px-captcha; web_extract -> "PerimeterX block"). It is a PASSIVE fingerprint + interactive
"Verify Your Identity" wall, so an exit node does NOT help. The trick that DOES work:
drive a REAL WINDOWED Chrome on the Mac over CDP, and CRUCIALLY warm the session on the
HOMEPAGE first, THEN navigate to product pages IN THE SAME TAB (location.assign). A cold
direct hit to /ip/... redirects to /blocked; a warmed same-tab navigation loads clean.

HOW TO RUN (on Sumeet's Mac, over Tailscale ssh sumeet@100.116.71.40):
  1. Launch windowed debug Chrome on a throwaway profile (NOT --headless; quote the glob):
       nohup "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
         --remote-debugging-port=9333 "--remote-allow-origins=*" \
         --user-data-dir=/tmp/scrape-profile --no-first-run --no-default-browser-check \
         --window-size=1280,900 >/tmp/scrape-chrome.log 2>&1 &
  2. python3 -m venv /tmp/scrape-venv && /tmp/scrape-venv/bin/pip install websocket-client
  3. base64-ship this file to the Mac, then:
       /tmp/scrape-venv/bin/python3 walmart_extract.py <url1> <url2> ...
  4. Cleanup: pkill -f "remote-debugging-port=9333"; rm -rf /tmp/scrape-profile /tmp/scrape-venv

Output per URL (JSON array to stdout):
  {url, name, brand, sku, price, currency, availability, image, composition,
   natural_pct, sizes:[{size,price,availability}], specs:{...}}

Example (verified 2026-08-19):
  George Kids Crew Neckline Tee 2-Pack 6000196741979 ->
    name "George Kids Crew Neckline Tee 2-Pack", brand George, $8 CAD, OutOfStock,
    composition "100% Cotton" (natural_pct 100), image i5.walmartimages.ca/asr/...jpeg
"""
import json, sys, time, urllib.request, websocket

CDP = "http://127.0.0.1:9333"
NATURAL = ("cotton","wool","linen","silk","cashmere","lyocell","tencel","hemp","merino","lambswool","alpaca","mohair","ramie","jute")

# JS runs in the page context after render; pulls JSON-LD + __NEXT_DATA__ specs + composition.
JS = r"""
(()=>{
  const out={url:location.href, title_tag:document.title};
  // ---- JSON-LD (Product or ProductGroup) ----
  const flat=[];
  const walk=o=>{if(!o)return;if(Array.isArray(o))o.forEach(walk);
    else if(typeof o==='object'){flat.push(o);if(o['@graph'])walk(o['@graph']);}};
  [...document.querySelectorAll('script[type="application/ld+json"]')].forEach(s=>{
    try{walk(JSON.parse(s.textContent));}catch(e){}});
  const isP=j=>{const t=j['@type'];return t==='Product'||t==='ProductGroup'||(Array.isArray(t)&&(t.includes('Product')||t.includes('ProductGroup')));};
  const prod=flat.find(isP);
  if(prod){
    out.name=prod.name; out.brand=prod.brand&&(prod.brand.name||prod.brand);
    out.image=Array.isArray(prod.image)?prod.image[0]:prod.image;
    out.sku=prod.sku||prod.mpn||prod.productID;
    // single-offer price
    let off=prod.offers; if(Array.isArray(off))off=off[0];
    if(off&&off.price!=null){out.price=off.price;out.currency=off.priceCurrency;
      out.availability=String(off.availability||'').replace('https://schema.org/','');}
    // ProductGroup per-size variants
    if(Array.isArray(prod.hasVariant)){
      out.sizes=prod.hasVariant.map(v=>{let o=v.offers;if(Array.isArray(o))o=o[0];o=o||{};
        return {size:v.size||v.name,price:o.price,availability:String(o.availability||'').replace('https://schema.org/','')};});
      if(out.price==null&&out.sizes.length){out.price=out.sizes[0].price;out.currency='CAD';}
    }
  }
  // ---- og fallback ----
  out.og_title=(document.querySelector('meta[property="og:title"]')||{}).content;
  if(!out.image)out.image=(document.querySelector('meta[property="og:image"]')||{}).content;
  // ---- __NEXT_DATA__ specifications ----
  try{
    const d=JSON.parse(document.getElementById('__NEXT_DATA__').textContent);
    const s=JSON.stringify(d.props.pageProps);
    const sm=s.match(/"specifications":(\[.*?\])/);
    if(sm){const specs=JSON.parse(sm[1]);const o={};specs.forEach(x=>o[x.name]=x.value);out.specs=o;}
    const dm=s.match(/"(?:longDescription|shortDescription)":"([^"]{0,600})"/);
    out.desc=dm?dm[1]:null;
  }catch(e){}
  // drop empty variant entries (other-colour variants carry no size/offer)
  if(out.sizes)out.sizes=out.sizes.filter(s=>s.size||s.price!=null);
  // ---- composition: prefer a Fabric/Material spec, else pull fibre pairs from desc/body ----
  let comp=null;
  if(out.specs){for(const k in out.specs){if(/fabric|material|composition/i.test(k)&&/%|cotton|polyester|wool|linen|nylon|elastane|spandex|viscose|rayon|silk/i.test(out.specs[k])){comp=out.specs[k];break;}}}
  if(!comp){const bt=(out.desc||'')+' '+(document.body?document.body.innerText:'');
    // capture each "NN% fibre" pair (fibre = 1-2 words), join them — avoids trailing prose
    const pairs=[...bt.matchAll(/(\d{1,3})\s*%\s*([A-Za-z]+(?:\s+[A-Za-z]+)?)/g)]
      .map(m=>m[1]+'% '+m[2].replace(/\b(these|the|is|are|with|and|soft|comfy|for)\b.*/i,'').trim())
      .filter(p=>!/%\s*$/.test(p));
    if(pairs.length){const seen={};const uniq=[];pairs.forEach(p=>{const k=p.toLowerCase();if(!seen[k]){seen[k]=1;uniq.push(p);}});comp=uniq.slice(0,4).join(', ');}
  }
  out.composition=comp;
  return out;
})()
"""

def new_tab():
    req = urllib.request.Request(CDP+"/json/new?about:blank", method="PUT")
    return json.load(urllib.request.urlopen(req))["webSocketDebuggerUrl"]

def send(ws, i, method, params=None):
    ws.send(json.dumps({"id":i,"method":method,"params":params or {}}))
    while True:
        m=json.loads(ws.recv())
        if m.get("id")==i: return m

def recv_until(ws, method, timeout=25):
    end=time.time()+timeout
    while time.time()<end:
        try: m=json.loads(ws.recv())
        except Exception: return
        if m.get("method")==method: return m

def natural_pct(comp):
    if not comp: return None
    import re
    total=0
    for pct,name in re.findall(r"(\d{1,3})\s*%\s*([A-Za-z]+)", comp):
        if any(nf in name.lower() for nf in NATURAL): total+=int(pct)
    return min(total,100) or None

def main():
    urls=sys.argv[1:]
    if not urls:
        print("usage: walmart_extract.py <url> [url...]", file=sys.stderr); sys.exit(1)
    ws=websocket.create_connection(new_tab(), timeout=30)
    send(ws,1,"Page.enable"); send(ws,2,"Runtime.enable")
    # WARM the session on the homepage first (defeats the cold-hit /blocked redirect)
    send(ws,3,"Page.navigate",{"url":"https://www.walmart.ca/en"})
    recv_until(ws,"Page.loadEventFired",25); time.sleep(12)
    results=[]; nid=100
    for u in urls:
        nid+=1; send(ws,nid,"Runtime.evaluate",{"expression":"location.assign(%r)"%u,"returnByValue":True})
        time.sleep(15)
        nid+=1; r=send(ws,nid,"Runtime.evaluate",{"expression":JS,"returnByValue":True})
        v=r.get("result",{}).get("result",{}).get("value",{}) or {}
        v["natural_pct"]=natural_pct(v.get("composition"))
        results.append(v)
    ws.close()
    print(json.dumps(results, indent=2))

if __name__=="__main__":
    main()

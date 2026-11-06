// generic_pdp.js — generic PDP probe for walled retailers on the iMac (mac_cdp_fetch.py).
// Reads JSON-LD Product/ProductGroup (name, price, availability, image, sku) + og tags + wall detection.
// Usage: costco-venv/bin/python mac_cdp_fetch.py generic_pdp.js <pdp-url> [...]
// Verified 2026-10-12 on RONA, Wayfair.ca, The Brick (see retailer-recipes.md for per-site results).
(() => { try {
  const t = document.title || '', body = (document.body && document.body.innerText) || '';
  const wall = /just a moment|access denied|press & hold|are you a robot|verify you are human|px-captcha|attention required/i;
  if (wall.test(t) || (body.length < 3000 && wall.test(body)))
    return (window.__gpT = (window.__gpT||0)+1) > 8 ? {ready:true, blocked:true, title:t, text:body.slice(0,300)} : {ready:false};
  if (document.readyState !== 'complete') return {ready:false};
  const lds = [];
  for (const s of document.querySelectorAll('script[type="application/ld+json"]')) {
    try { const j = JSON.parse(s.textContent); (Array.isArray(j)?j:(j['@graph']||[j])).forEach(x=>lds.push(x)); } catch(e){}
  }
  const prod = lds.find(x => /Product/.test([].concat(x['@type']).join(',')));
  if (!prod && (window.__gpN=(window.__gpN||0)+1) < 6) return {ready:false};
  const og = p => (document.querySelector(`meta[property="${p}"]`)||{}).content || null;
  let offers = prod ? [].concat(prod.offers || []) : [];
  if (prod && prod.hasVariant) offers = offers.concat(...[].concat(prod.hasVariant).map(v=>[].concat(v.offers||[])));
  const o = offers.map(x => x && x['@type']==='AggregateOffer' ? {price:x.lowPrice, high:x.highPrice, currency:x.priceCurrency, availability:x.availability} :
                     {price:x.price, currency:x.priceCurrency, availability:(x.availability||'').replace(/.*\//,''), sku:x.sku});
  const priceText = (body.match(/\$\s?[\d,]+\.\d\d/g) || []).slice(0,6);
  return {ready:true, title:t, name: prod ? prod.name : og('og:title'),
          brand: prod && prod.brand ? (prod.brand.name || prod.brand) : null,
          sku: prod ? (prod.sku || prod.productID || null) : null,
          image: prod ? [].concat(prod.image||[])[0] : og('og:image'),
          offers: o.slice(0,12), n_offers:o.length, price_text: priceText,
          ld_types: lds.map(x=>[].concat(x['@type']).join(',')).slice(0,10)};
} catch(e) { return {ready:true, err:String(e)}; } })()

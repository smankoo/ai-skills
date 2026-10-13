// etsy_pdp.js — Etsy Canada listing or search page on the iMac (verified 2026-10-13).
// VPS: DataDome/JS challenge on etsy.com (curl 403, web_extract captcha). iMac Chrome loads /ca/ pages clean.
// Usage (iMac):
//   costco-venv/bin/python mac_cdp_fetch.py etsy_pdp.js "https://www.etsy.com/ca/listing/<id>/<slug>"
//   costco-venv/bin/python mac_cdp_fetch.py etsy_pdp.js "https://www.etsy.com/ca/search?q=<words>"
// Listing: JSON-LD Product -> name, sku (= listing id), offers.price (CAD, the SALE price when on sale),
//   offers.eligibleQuantity (units left), availability, shippingOrigin country; brand = shop name.
//   Original price: DOM `.wt-text-strikethrough` inside the buy box (`[data-buy-box-region="price"]`).
//   Variations (size/colour selects) are `select[id^="variation-selector"]`; options carry "[Sold out]" text.
// Search: listing cards `[data-listing-id]` with `.n-listing-card__price .currency-value`; ads have `.wt-badge` "Ad"
//   / data-is-ad. Etsy prices from non-CA shops can add import costs; check shipping origin on the listing.
(() => { try {
  if (document.readyState !== 'complete') return {ready:false};
  const t = document.title || '', body = (document.body && document.body.innerText) || '';
  if (/are you a robot|verify|captcha|access denied/i.test(t) || (body.length < 2000 && /captcha|robot/i.test(body)))
    return (window.__eN=(window.__eN||0)+1) > 8 ? {ready:true, blocked:true, title:t} : {ready:false};
  const tx = e => e ? e.innerText.replace(/\s+/g,' ').trim() : null;
  const num = s => { const m=(s||'').replace(/,/g,'').match(/(\d+(?:\.\d\d)?)/); return m ? parseFloat(m[1]) : null; };
  if (/\/search/.test(location.pathname)) {
    const cards = [...document.querySelectorAll('[data-listing-id]')].filter(c=>c.querySelector('a[href*="/listing/"]'));
    if (!cards.length) return (window.__eS=(window.__eS||0)+1) > 8 ? {ready:true, items:[], note:'no cards'} : {ready:false};
    const seen = new Set(), items = [];
    for (const c of cards) {
      const id = c.getAttribute('data-listing-id'); if (seen.has(id)) continue; seen.add(id);
      const a = c.querySelector('a[href*="/listing/"]'), img = c.querySelector('img');
      const prices = [...c.querySelectorAll('.currency-value')].map(e=>num(e.innerText)).filter(x=>x!=null);
      const ad = /(^|\n)\s*Ad\b|\bAd (by|from) /.test(c.innerText || '') || c.getAttribute('data-is-ad')==='true' || /ad_|\bref=sc_gallery.*ad/i.test(a.href);
      items.push({id, ad, name: (tx(c.querySelector('h3, h2')) || (a.title||'')).slice(0,140),
        url: a.href.split('?')[0], price: prices[0] ?? null, was: prices.length>1 && prices[1]>prices[0] ? prices[1] : null,
        image: img ? (img.src || img.getAttribute('data-src')) : null});
    }
    return {ready:true, kind:'search', q:new URLSearchParams(location.search).get('q'), n:items.length,
            items: items.filter(i=>!i.ad).slice(0,24), ads_dropped: items.filter(i=>i.ad).length};
  }
  const lds = [];
  for (const s of document.querySelectorAll('script[type="application/ld+json"]')) {
    try { const j = JSON.parse(s.textContent); (Array.isArray(j)?j:(j['@graph']||[j])).forEach(x=>lds.push(x)); } catch(e){}
  }
  const p = lds.find(x => /Product/.test([].concat(x['@type']).join(',')));
  if (!p) return (window.__eP=(window.__eP||0)+1) > 8 ? {ready:true, err:'no Product JSON-LD', title:t} : {ready:false};
  const o = [].concat(p.offers||[])[0] || {};
  const dec = s => { const d=document.createElement('textarea'); d.innerHTML=s||''; return d.value; };
  const box = document.querySelector('[data-buy-box-region="price"]') || document;
  const wasE = box.querySelector('.wt-text-strikethrough');
  const vsel = [...document.querySelectorAll('select[id^="variation-selector"]')].map(s => ({
    label: tx(document.querySelector(`label[for="${s.id}"]`)),
    options: [...s.options].filter(x=>x.value).map(x=>x.text.replace(/\s+/g,' ').trim()).slice(0,30)}));
  return {ready:true, kind:'listing', id:p.sku || (location.pathname.match(/listing\/(\d+)/)||[])[1],
    name: dec(p.name), shop: p.brand ? (p.brand.name||p.brand) : null,
    price: o.price!=null ? Number(o.price) : (o.lowPrice!=null ? Number(o.lowPrice) : null), high: o.highPrice!=null ? Number(o.highPrice) : null,
    currency: o.priceCurrency || null, was: wasE ? num(wasE.innerText) : null,
    availability: (o.availability||'').replace(/.*\//,''), qty_left: o.eligibleQuantity ?? null,
    ships_from: o.shippingDetails && o.shippingDetails.shippingOrigin ? o.shippingDetails.shippingOrigin.addressCountry : null,
    rating: p.aggregateRating ? {value:Number(p.aggregateRating.ratingValue), count:Number(p.aggregateRating.reviewCount)} : null,
    image: (document.querySelector('meta[property="og:image"]')||{}).content || [].concat(p.image||[]).map(i=>i.contentURL||i)[0] || null,
    variations: vsel, description: dec(p.description||'').slice(0,400)};
} catch(e) { return {ready:true, err:String(e)}; } })()

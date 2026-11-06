// wayfair_pdp.js — Wayfair.ca product page on the iMac (VPS: PerimeterX px-captcha; iMac loads PDPs clean 2026-10-12).
// Usage (iMac): costco-venv/bin/python mac_cdp_fetch.py wayfair_pdp.js "https://www.wayfair.ca/<dept>/pdp/<slug>-<sku>.html"
// No Product JSON-LD. Stable hooks are data-test-id attributes:
//   [data-test-id="PricingFull-leadPrice"]          current price
//   [data-test-id="PricingFull-strikethroughPrice"] "was $X"
//   h1 = name; og:image = image; SKU = the trailing c123456789 / abc1234 in the URL
// Availability/delivery: scanned from body text ("Out of Stock", "Get it by <date>", "Free Shipping").
(() => { try {
  if (/press & hold|access to this page has been denied|px-captcha/i.test(document.title + ' ' + ((document.body||{}).innerText||'').slice(0,500)))
    return {ready:true, blocked:true, title:document.title};
  const q = s => document.querySelector(s), tx = e => e ? e.innerText.replace(/\s+/g,' ').trim() : null;
  const lead = q('[data-test-id="PricingFull-leadPrice"]');
  if (!lead || document.readyState !== 'complete') return {ready:false};
  const num = t => { const m = (t||'').match(/\$\s?([\d,]+(?:\.\d\d)?)/); return m ? parseFloat(m[1].replace(/,/g,'')) : null; };
  const body = document.body.innerText;
  const oos = /\bOut of Stock\b|\bCurrently unavailable\b|\bNo longer available\b/i.test(body.slice(0, 20000));
  const getBy = (body.match(/(?:Get it by|Arrives by|Delivery by)[^\n]{0,60}/i)||[null])[0];
  const freeShip = /Free Shipping/i.test(body.slice(0, 20000));
  return {ready:true,
    sku: (location.pathname.match(/-([a-z]*\d{5,})\.html/i)||[])[1] || null,
    name: tx(q('h1')),
    price: num(tx(lead)),
    was: num(tx(q('[data-test-id="PricingFull-strikethroughPrice"]'))),
    out_of_stock: oos, delivery: getBy, free_shipping: freeShip,
    // og:image is often missing and the first <img> can be a 50px swatch: upsize resize-hNN-wNN to 800 (verified 2026-10-13, 200 image/jpeg)
    image: (q('meta[property="og:image"]')||{}).content ||
           (([...document.querySelectorAll('img[src*="assets.wfcdn.com/im/"]')].map(i=>i.src).find(u=>/compr|resize/.test(u)) || '')
              .replace(/resize-h\d+-w\d+/, 'resize-h800-w800') || null)};
} catch(e) { return {ready:true, err:String(e)}; } })()

// rona_pdp.js — RONA (rona.ca) product page on the iMac (VPS: Cloudflare/DataDome; verified 2026-10-12).
// Usage (iMac): costco-venv/bin/python mac_cdp_fetch.py rona_pdp.js "https://www.rona.ca/en/product/<slug>-<8-digit id>"
// No Product JSON-LD (only BreadcrumbList), so read the DOM:
//   price  .price-box__price (text "$ 219 each"); was price .price-box__regular-price / [class*="old-price"]
//   stock  .plp-stock-message-new ("10 in Store") for the store in the body class "store-<n>"
//   pickup .pdp-bopis-promise-message; delivery .pdp-delivery-best-customer-promise
//   image  og:image or https://cdn.rona.ca/images/<id>_L.jpg
(() => { try {
  if (/just a moment|access denied/i.test(document.title)) return {ready:true, blocked:true, title:document.title};
  const q = s => document.querySelector(s), tx = e => e ? e.innerText.replace(/\s+/g,' ').trim() : null;
  const pe = q('.price-box--product-page .price-box__price') || q('.price-box__price');
  if (!pe || document.readyState !== 'complete') return {ready:false};
  const num = t => { const m = (t||'').replace(/\s/g,'').match(/\$([\d,]+(?:\.\d\d)?)/); return m ? parseFloat(m[1].replace(/,/g,'')) : null; };
  const wasE = q('.price-box--product-page [class*="regular"]') || q('.price-box--product-page [class*="old"]') || q('.price-box--product-page s');
  const stockT = tx(q('.page-product .plp-stock-message-new') || q('.plp-stock-message-new'));
  const sm = (document.body.className + ' ' + [...document.querySelectorAll('[class*="store-"]')].slice(0,5).map(e=>e.className).join(' ')).match(/store-(\d{4,6})/);
  const id = (location.pathname.match(/-(\d{8})(?:$|[/?#])/)||[])[1] || null;
  return {ready:true,
    id, name: tx(q('h1')),
    price: num(tx(pe)), price_text: tx(pe),
    was: wasE ? num(tx(wasE)) : null,
    store_id: sm ? sm[1] : null,               // the iMac profile's store; stock_text refers to it
    stock_text: stockT, store_qty: stockT && /(\d+)\s+in\s+store/i.test(stockT) ? parseInt(stockT.match(/(\d+)\s+in\s+store/i)[1]) : null,
    pickup: tx(q('.pdp-bopis-promise-message')),
    delivery: tx(q('.pdp-delivery-best-customer-promise')),
    image: (q('meta[property="og:image"]')||{}).content || (id ? `https://cdn.rona.ca/images/${id}_L.jpg` : null)};
} catch(e) { return {ready:true, err:String(e)}; } })()

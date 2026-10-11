// iherb_pdp.js — iHerb CA extractor for mac_cdp_fetch.py (iMac CDP 9334). Verified 2026-10-11.
// Works on BOTH page types:
//   https://ca.iherb.com/search?kw=<q>        -> {kind:'search', items:[{pid,part,title,brand,price,oos,sponsored,url,img}]}
//   https://ca.iherb.com/pr/<slug>/<pid>      -> {kind:'pdp', name, price, list_price, currency, availability,
//                                                  protein_g, serving, servings, certs[], img, url}
// Search tiles: a.product-link carries data-ga-discount-price, data-ga-is-out-of-stock,
//   data-sponsored, data-part-number. PDP: JSON-LD Product offers + Supplement Facts table text.
// The VPS browser passes Cloudflare on /search but gets "Just a moment" forever on /pr/ pages.
(() => {
  const t = document.title || '';
  if (/just a moment|attention required/i.test(t)) return {ready: false, wall: t};
  const u = location.href;
  if (/\/search\?/.test(u)) {
    const seen = new Set(), items = [];
    document.querySelectorAll('a.product-link[data-product-id]').forEach(a => {
      const pid = a.dataset.productId; if (seen.has(pid)) return; seen.add(pid);
      const c = a.closest('.product-inner') || a.parentElement;
      items.push({pid, part: a.dataset.partNumber, title: a.title, brand: a.dataset.gaBrandName,
        price: parseFloat(a.dataset.gaDiscountPrice) || null, oos: a.dataset.gaIsOutOfStock === 'True',
        sponsored: a.dataset.sponsored === 'True', url: a.href, img: c && c.querySelector('img') ? c.querySelector('img').src : null});
    });
    if (!items.length) return {ready: false};
    return {ready: true, kind: 'search', n: items.length, items: items.filter(i => !i.sponsored).slice(0, 24)};
  }
  let prod = null;
  for (const s of document.querySelectorAll('script[type="application/ld+json"]')) {
    try { const j = JSON.parse(s.textContent); const arr = Array.isArray(j) ? j : [j];
      for (const x of arr) if (x && x['@type'] === 'Product') prod = x; } catch (e) {}
  }
  if (!prod) return {ready: false};
  let off = prod.offers || {}; if (Array.isArray(off)) off = off[0] || {};
  const body = document.body.innerText;
  const sfIdx = body.search(/Supplement Facts|Nutrition Facts/i);
  const sf = sfIdx >= 0 ? body.slice(sfIdx, sfIdx + 1500) : '';
  const pm = sf.match(/Protein\s*\t?\s*(\d+(?:\.\d+)?)\s*g/i);
  const ss = sf.match(/Serving Size[:\s]*([^\n]+)/i);
  const sp = sf.match(/Servings Per Container[:\s]*([^\n]+)/i);
  const certs = [...new Set((body.match(/(NSF Certified for Sport|Informed[- ]Sport|Informed Choice|USDA Organic|Non-GMO Project Verified|Halal|Kosher)/gi) || []).map(s => s.trim()))];
  const listEl = document.querySelector('#product-price .price-inner-text, .list-price, [class*=strike]');
  return {ready: true, kind: 'pdp', name: prod.name, brand: prod.brand && (prod.brand.name || prod.brand),
    sku: prod.sku || prod.mpn, price: parseFloat(off.price) || null, currency: off.priceCurrency,
    list_price: listEl ? listEl.innerText.replace(/\s+/g, ' ').trim() : null,
    availability: (off.availability || '').split('/').pop(),
    protein_g: pm ? parseFloat(pm[1]) : null, serving: ss ? ss[1].trim() : null,
    servings: sp ? sp[1].trim() : null, certs,
    img: (Array.isArray(prod.image) ? prod.image[0] : prod.image) || null, url: u};
})()

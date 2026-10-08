// ua_pdp.js: Under Armour Canada PDP extractor (verified 2026-10-08).
// Runs in a real browser tab on underarmour.ca (VPS browser_exec works; curl gets HTTP 418).
// Usage A (VPS browser_exec): goto_url(pdp); wait ~8 s; js(open('ua_pdp.js').read())
// Usage B (iMac): mac_cdp_fetch.py ua_pdp.js <pdp-url>
// Optional filter: set window.__UA_SIZES = ['10.5','11'] before evaluating.
// Returns {ready, name, width, price, list_price, on_sale, currency, image, colours:{<code colour>:{in:[], out:[]}}, composition}
(() => {
  const lds = [...document.querySelectorAll('script[type="application/ld+json"]')]
    .map(s => { try { return JSON.parse(s.textContent); } catch (e) { return null; } }).filter(Boolean);
  const g = lds.find(j => j['@type'] === 'ProductGroup' || j['@type'] === 'Product');
  if (!g) return {ready: false, title: document.title};
  const want = window.__UA_SIZES || null;
  const vars = g.hasVariant || [g];
  const colours = {};
  let price = null;
  for (const v of vars) {
    const code = (v.sku || '').split('-')[1] || '';
    const key = code + ' ' + (v.color || '');
    colours[key] = colours[key] || {in: [], out: [], image: v.image};
    if (want && !want.includes(String(v.size))) continue;
    const o = v.offers || {};
    if (o.price != null) { price = price == null ? +o.price : Math.min(price, +o.price); colours[key].price = +o.price; }
    (/InStock|LimitedAvailability/.test(o.availability || '') ? colours[key].in : colours[key].out).push(String(v.size));
  }
  // visible price (selected colour): .bfx-list-price (was) + .bfx-sale-price (now) when on sale
  const num = sel => { const e = document.querySelector(sel); return e ? +e.textContent.replace(/[^\d.]/g, '') : null; };
  const list = num('.bfx-list-price'), sale = num('.bfx-sale-price');
  const nums = [sale || list, list].filter(x => x != null);
  const name = g.alternateName || g.name;
  const w = (name.match(/\b(Wide|Extra Wide)\s*\((2E|4E|D|2E)\)|\((2E|4E)\)/i) || [''])[0];
  const body = document.body.innerText;
  const comp = [...new Set(body.match(/\d{1,3}% [A-Z][a-z]+(?: [a-z]+)?/g) || []).filter(s => !/ Off\b/.test(s))].slice(0, 6);
  return {ready: true, name, url: location.href.split('?')[0], width: w || 'Regular (D)',
          currency: (g.offers || {}).priceCurrency || 'CAD', min_variant_price: price,
          price_selected_colour: nums[0], list_price: list, on_sale: !!(sale && list && sale < list),
          image: Array.isArray(g.image) ? g.image[0] : g.image, composition: comp, colours};
})()

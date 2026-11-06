// nb_pdp.js: New Balance Canada PDP extractor for mac_cdp_fetch.py (verified 2026-10-08).
// newbalance.ca is Akamai-walled from the VPS (curl 403 634 B, web_extract 403, VPS Chrome "Oops! error code").
// iMac residential Chrome renders it fine. Data source: the ProductGroup JSON-LD on the PDP.
// WIDTH lives in the variant SKU: <STYLE+COLOUR>-<WIDTH>-<SIZE>, e.g. M880B15-2E-105 = width 2E, size 10.5.
// Men's widths seen: D (standard), 2E (wide), 4E (extra wide); some models also B / 6E.
// Set window.__NB_SIZES = ['10.5','11'] and/or window.__NB_WIDTHS = ['2E','4E'] to filter (mac_cdp_fetch can't pass args,
// so instead edit the two constants below or make a copy).
// Returns {ready, name, url, currency, price, list_price, colours:{COLOUR:{image, widths:{W:{in:[], out:[]}}}}}
(() => {
  const SIZES = window.__NB_SIZES || ['10.5', '11'];
  const WIDTHS = window.__NB_WIDTHS || null;  // null = all widths
  const lds = [...document.querySelectorAll('script[type="application/ld+json"]')]
    .map(s => { try { return JSON.parse(s.textContent); } catch (e) { return null; } }).filter(Boolean);
  const g = lds.find(j => j['@type'] === 'ProductGroup' && Array.isArray(j.hasVariant));
  if (!g) return {ready: false, title: document.title};
  const colours = {};
  let minPrice = null;
  for (const v of g.hasVariant) {
    const parts = (v.sku || '').split('-');
    const width = parts.length >= 3 ? parts[parts.length - 2] : '?';
    const size = String(v.size);
    if (SIZES && !SIZES.includes(size)) continue;
    if (WIDTHS && !WIDTHS.includes(width)) continue;
    const c = (parts[0] || '') + ' ' + (v.color || '?');  // key by style+colour: two styles can share a colour name
    colours[c] = colours[c] || {style: parts[0], image: (v.image || '').replace(/\?.*$/, '') + '?$dw_detail_main_lg$', widths: {}};
    const w = colours[c].widths[width] = colours[c].widths[width] || {in: [], out: [], price: null};
    const o = v.offers || {};
    w.price = o.price != null ? +o.price : w.price;
    if (o.price != null) minPrice = minPrice == null ? +o.price : Math.min(minPrice, +o.price);
    const bucket = /InStock|LimitedAvailability|PreOrder/.test(o.availability || '') ? w.in : w.out;
    if (!bucket.includes(size)) bucket.push(size);  // JSON-LD repeats some SKUs
  }
  // Visible price block (selected colour): sale shows "$151.99 $189.99"
  const pt = (document.querySelector('.prices, .price, [class*="product-price"]') || {}).innerText || '';
  const nums = (pt.match(/\$\s?\d+(?:\.\d\d)?/g) || []).map(s => +s.replace(/[^\d.]/g, ''));
  return {ready: true, name: g.name, url: g.url, currency: 'CAD', min_price_filtered: minPrice,
          visible_price: nums[0] || null, list_price: nums.length > 1 ? Math.max(...nums) : null,
          filter: {sizes: SIZES, widths: WIDTHS}, n_variants: g.hasVariant.length, colours};
})()

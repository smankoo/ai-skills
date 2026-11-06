// levi_pdp.js — Levi's CA PDP extractor for the iMac (mac_cdp_fetch.py, CDP 9334). Verified 2026-10-10.
// Usage: scp -q levi_pdp.js sumeet@100.119.136.41:.hermes/
//        ssh sumeet@100.119.136.41 'cd ~/.hermes && costco-venv/bin/python mac_cdp_fetch.py levi_pdp.js <pdp_url>'
// VPS is Akamai-walled (curl 403 / web_extract blocked) — iMac only.
// Returns {ready, name, sku, price, avail, image, composition,
//          sizes:{Waist:[{v, in_stock}], Length:[...]} (or Size: for tops)}
// OOS marker: button.size-tile-list-button gets class "unavailable" + aria-disabled="true";
// aria-label is "Waist 28 " / "Length 32 " / "Size M ". JSON-LD is ONE Product per colour (no per-size variants).
// Waist and length tiles are independent axes: a waist tile shows availability for the currently
// selected length (page default), so for an exact W×L check, click the length first (not done here).
(() => {
  if (!document.querySelector('h1')) return {ready: false};
  const btns = [...document.querySelectorAll('button.size-tile-list-button')];
  if (!btns.length) return {ready: false, why: 'no size tiles yet'};
  const lds = [...document.querySelectorAll('script[type="application/ld+json"]')]
    .map(s => { try { return JSON.parse(s.textContent); } catch (e) { return null; } }).filter(Boolean)
    .flatMap(j => Array.isArray(j) ? j : (j['@graph'] || [j]));
  const g = lds.find(j => /Product/.test(j['@type'] || '')) || {};
  const v = (g.hasVariant || [g])[0] || {};
  const o = Array.isArray(v.offers) ? v.offers[0] : (v.offers || g.offers || {});
  const sizes = {};
  for (const b of btns) {
    const al = (b.getAttribute('aria-label') || '').trim();
    const axis = (al.match(/^([A-Za-z]+)/) || [null, 'Size'])[1];
    const val = b.innerText.trim();
    (sizes[axis] = sizes[axis] || []);
    if (!sizes[axis].some(x => x.v === val))
      sizes[axis].push({v: val, in_stock: !(b.classList.contains('unavailable') || b.getAttribute('aria-disabled') === 'true')});
  }
  const t = document.body.innerText;
  const i = t.search(/Composition\s*&\s*Care/i);
  const compBlock = i >= 0 ? t.slice(i, i + 400) : '';
  const cm = compBlock.match(/\d{1,3}\s*%\s*[A-Za-z][^\n]{0,120}/);
  const img = Array.isArray(g.image) ? g.image[0] : g.image;
  const pt = [...document.querySelectorAll('[class*=price]')].map(e => e.innerText.trim()).filter(x => /\$\d/.test(x))[0] || '';
  return {ready: true, name: v.name || g.name, sku: v.sku || g.sku, price: o.price, currency: o.priceCurrency,
          price_text: pt.replace(/\s+/g, ' ').slice(0, 80),
          avail: String(o.availability || '').replace(/^https?:\/\/schema\.org\//, ''),
          image: img || (document.querySelector('meta[property="og:image"]') || {}).content,
          composition: cm ? cm[0].trim() : null, sizes};
})()

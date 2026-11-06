// adidas_pdp.js: adidas Canada PDP extractor for mac_cdp_fetch.py (verified 2026-10-08).
// adidas.ca: VPS curl times out (000), web_extract 403, VPS Chrome gets the "WAFfailover" shell.
// iMac residential Chrome renders it. Once the PDP is loaded, same-origin fetch() to the site's own
// JSON API works: /api/products/<ARTICLE> (name, pricing, attributes) and
// /api/products/<ARTICLE>/availability (variation_list[]: size, availability, availability_status).
// adidas.ca sells NO width variants for most running shoes; a few models have a separate "Wide" article
// (its name contains "Wide"). Width is NOT a size attribute, so check the product name.
(async () => {
  const m = location.pathname.match(/\/([A-Z0-9]{6})\.html/);
  if (!m) return {ready: false, why: 'no article id', url: location.href};
  const id = m[1];
  if (!document.querySelector('h1')) return {ready: false};
  const J = async u => { const r = await fetch(u, {credentials: 'include'}); return r.ok ? r.json() : {_status: r.status}; };
  const p = await J(`/api/products/${id}?sitePath=en`);
  const a = await J(`/api/products/${id}/availability?sitePath=en`);
  const want = window.__AD_SIZES || ['10.5', '11', 'M 10.5 / W 11.5', 'M 11 / W 12'];
  const sizes = (a.variation_list || []).map(v => ({size: v.size, status: v.availability_status, qty_flag: v.availability}));
  const pi = p.pricing_information || {};
  const ai = p.attribute_list || {};
  return {ready: true, id, name: p.name || (document.querySelector('h1') || {}).innerText,
          colour: ai.color || (p.product_description || {}).subtitle,
          currency: 'CAD', price: pi.currentPrice, list_price: pi.standard_price, sale_price: pi.sale_price,
          wide_in_name: /wide/i.test(p.name || ''),
          image: (document.querySelector('meta[property="og:image"]') || {}).content,
          overall: a.availability_status,
          sizes_wanted: sizes.filter(s => want.some(w => s.size === w || s.size.startsWith('M ' + w + ' ') || s.size === w)),
          all_sizes: sizes.map(s => s.size + ':' + s.status).join(' '),
          api_status: {product: p._status || 200, availability: a._status || 200}};
})()

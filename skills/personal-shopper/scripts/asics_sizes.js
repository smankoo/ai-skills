// asics_sizes.js (rewritten 2026-10-09): ASICS CA per-colour x per-size availability from a rendered PDP.
// Run via the iMac (VPS browser + curl are Akamai "Access Denied"; web_extract renders but has no stock):
//   scp -q asics_sizes.js sumeet@100.119.136.41:.hermes/
//   ssh sumeet@100.119.136.41 'cd ~/.hermes && costco-venv/bin/python mac_cdp_fetch.py asics_sizes.js <pdp-url>'
// WIDTH: ASICS sells each width as its OWN style/URL: men "<MODEL>" = D (standard), "<MODEL> WIDE" = 2E,
// "<MODEL> EXTRA WIDE" = 4E (women: B / WIDE = D / EXTRA WIDE = 2E). So "is 4E in stock in size X" =
// load the EXTRA WIDE style's PDP and read size X here. `width` comes from utag_data.product_width.
// DATA SOURCE (2026-10-09): the Magento `jsonConfig` x-magento-init block is GONE from the PDP (the old
// version of this script returned {ready:false} forever). The Tealium `window.utag_data` object now carries
// parallel arrays, one entry per simple product (colour x size):
//   product_colors[i]  = 3-digit colour code (matches the URL suffix, e.g. -002)
//   product_sizes[i]   = size label ("10H" = US 10.5)
//   product_sizes_stock[i] = "yes" | "no"
//   product_price / product_marked_down_price / product_width / product_variant (selected colour name)
// Cross-check: for the selected colour these matched the size buttons' `.swatch-option.disabled` class exactly.
// Output: {ready, url, name, price, sale_price, width, image, selected_colour, matrix:[{colour_code, sizes:[{size,in_stock}]}],
//          dom_sizes:[{size, disabled}] (selected colour only)}
(() => {
  if (/Access Denied/i.test(document.title)) return {ready: true, blocked: true, title: document.title};
  const u = window.utag_data;
  const h1 = ((document.querySelector('h1') || {}).innerText || '').trim();
  if (!u || !h1 || !Array.isArray(u.product_sizes)) return {ready: false, title: document.title};
  const cols = u.product_colors || [], sizes = u.product_sizes, stock = u.product_sizes_stock || [];
  const by = {};
  sizes.forEach((s, i) => {
    const c = cols[i] || '?';
    const sz = String(s).replace(/H$/, '.5');
    by[c] = by[c] || {};
    // the arrays can repeat a (colour,size) pair at the ends; any "yes" wins
    by[c][sz] = by[c][sz] || stock[i] === 'yes';
  });
  const num = x => parseFloat(x) || 0;
  const matrix = Object.entries(by).map(([c, m]) => ({colour_code: c,
    sizes: Object.entries(m).sort((a, b) => num(a[0]) - num(b[0])).map(([size, in_stock]) => ({size, in_stock}))}));
  const dom_sizes = [...document.querySelectorAll('.swatch-attribute.size .swatch-option')].map(e => ({
    size: (e.getAttribute('aria-label') || e.innerText || '').trim().replace(/H$/, '.5'),
    disabled: /\bdisabled\b/.test(e.className)}));
  const first = a => Array.isArray(a) ? a[0] : a;
  const price = num(first(u.product_price)), md = num(first(u.product_marked_down_price));
  return {ready: true, url: location.href, name: h1, currency: u.site_currency || 'CAD',
          price, sale_price: md && md < price ? md : null,
          width: first(u.product_width) || null, selected_colour: first(u.product_variant) || null,
          url_colour_code: (location.pathname.match(/-(\d{3})(?:$|[/?])/) || [])[1] || null,
          image: (document.querySelector('meta[property="og:image"]') || {}).content ||
                 ([...document.images].map(i => i.src).find(s => /assetsadobe\.com\/is\/image\/asics/.test(s)) || null),
          matrix, dom_sizes};
})()

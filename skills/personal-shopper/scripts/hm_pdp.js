// hm_pdp.js — H&M Canada PDP extractor for the iMac (mac_cdp_fetch.py, CDP 9334). Verified 2026-10-10.
// Usage: scp -q hm_pdp.js sumeet@100.119.136.41:.hermes/
//        ssh sumeet@100.119.136.41 'cd ~/.hermes && costco-venv/bin/python mac_cdp_fetch.py hm_pdp.js https://www2.hm.com/en_ca/productpage.<10digit>.html'
// Why the iMac: on 2026-10-10 the VPS got Akamai "Access Denied" in curl, in web_extract AND in the VPS browser.
// Data: JSON-LD ProductGroup.hasVariant[] (per colour x size: sku, name "… - Colour", size, offers.price,
//       offers.availability) + per-article `compositions`, `whitePriceValue` (regular) and `redPriceValue`
//       (sale) from __NEXT_DATA__, anchored on this article's size codes (colours can differ in fibre!). Returns only the colour in the URL by default
//       (article = first 10 digits of sku); set window.__HM_ALL=1 for all colours.
(() => {
  if (!document.querySelector('h1')) return {ready: false};
  const lds = [...document.querySelectorAll('script[type="application/ld+json"]')]
    .map(s => { try { return JSON.parse(s.textContent); } catch (e) { return null; } }).filter(Boolean)
    .flatMap(j => Array.isArray(j) ? j : [j]);
  const g = lds.find(j => j['@type'] === 'ProductGroup');
  if (!g || !(g.hasVariant || []).length) return {ready: false, why: 'no ProductGroup yet'};
  const art = (location.pathname.match(/productpage\.(\d{10})/) || [])[1];
  const vars = g.hasVariant.map(v => {
    const o = Array.isArray(v.offers) ? v.offers[0] : (v.offers || {});
    return {sku: v.sku, article: String(v.sku || '').slice(0, 10), colour: v.color || (v.name || '').split(' - ').pop(),
            size: v.size, price: o.price, currency: o.priceCurrency,
            in_stock: /InStock/i.test(String(o.availability || '')), image: v.image};
  });
  const mine = window.__HM_ALL ? vars : vars.filter(v => v.article === art);
  // Per-article block in __NEXT_DATA__: ...sizes[{sizeCode:"<art><3>",name:"M"}],"whitePrice","redPrice",
  // ..."compositions":["Cotton 95%, Viscose 5%"]. Colours of one product can differ in fibre, so anchor on THIS article.
  let comps = [], white = null, red = null;
  try {
    const nd = (document.getElementById('__NEXT_DATA__') || {}).textContent || '';
    // map each "compositions" block to the article code of the size list just before it
    const re = /"compositions":\[([^\]]*)\]/g; let m;
    while ((m = re.exec(nd))) {
      const before = nd.slice(Math.max(0, m.index - 3000), m.index);
      const codes = [...before.matchAll(/"(\d{10})\d{3}"/g)];
      if (!codes.length || codes[codes.length - 1][1] !== art) continue;
      comps = JSON.parse('[' + m[1] + ']');
      const w = before.match(/"whitePriceValue":"([\d.]+)"/), r = before.match(/"redPriceValue":"([\d.]+)"/);
      white = w ? +w[1] : null; red = r ? +r[1] : null;
      break;
    }
  } catch (e) {}
  const natural = (() => { const c = (comps[0] || ''); const m = [...c.matchAll(/([A-Za-z ]+?)\s*(\d{1,3})%/g)];
    if (!m.length) return null; return m.filter(x => /cotton|wool|linen|silk|cashmere|lyocell|hemp|merino|alpaca|mohair|ramie/i.test(x[1])).reduce((a, x) => a + +x[2], 0); })();
  const prices = [...document.querySelectorAll('[class*=price i]')].map(e => e.innerText.trim()).filter(x => /\$\d/.test(x));
  return {ready: true, name: g.name, material: g.material, composition: comps, natural_pct: natural,
          price: red || white, regular: white, on_sale: !!(red && white && red < white),
          price_text: prices.slice(0, 3), article: art,
          sizes: mine.map(v => ({size: v.size, colour: v.colour, price: v.price, in_stock: v.in_stock})),
          image: (mine[0] || {}).image, n_variants_all: vars.length};
})()

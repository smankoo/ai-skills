// simons_pdp.js (2026-10-09): La Maison Simons product page -> name, brand, CAD price, per-colour x per-size
// stock COUNT, composition, image. Run in the VPS browser (browser_exec); deep PDP URLs load clean there
// (curl from the VPS = Cloudflare 403; /en/search and some category URLs bounce to the homepage).
//   goto_url(pdp_url); wait_for_load(); time.sleep(6)
//   print(js(open('<skills>/personal-shopper/scripts/simons_pdp.js').read()))
// Find PDP URLs with web_search 'site:simons.ca <brand> <item>'. Shape: /en/<dept>/<cat>/<sub>/<slug>--<id1>-<id2>
// Data sources (verified 2026-10-09):
//   - JSON-LD Product: name, brand.name, offers.price / priceCurrency / availability, image
//   - an inline <script> holding {"<colourCode>":{"size":[{key,label,skuId,rawListPrice,rawSalePrice,stockLevel}]}}
//     -> stockLevel is a real unit count; "0" = sold out in that colour+size
//   - colour names: label[for^="colorInput<code>-"] (aria-label/title), else the code only
//   - composition: .compositionAndCare-composition .compositionAndCare-wrapper (e.g. "100% organic cotton")
// Returns a JSON string.
(() => {
  const ld = [...document.querySelectorAll('script[type="application/ld+json"]')]
    .map(s => { try { return JSON.parse(s.textContent); } catch (e) { return null; } }).filter(Boolean).flat();
  const p = ld.find(j => /Product/.test(j['@type'] || '')) || {};
  const o = Array.isArray(p.offers) ? p.offers[0] : (p.offers || {});
  let stock = null;
  for (const s of document.scripts) {
    const x = s.textContent.trim();
    if (!/"stockLevel"/.test(x) || x.length > 300000) continue;
    const st = x.indexOf('{');
    try { const j = JSON.parse(x.slice(st)); if (Object.values(j).some(v => v && Array.isArray(v.size))) { stock = j; break; } } catch (e) {}
  }
  const colourName = code => {
    const l = document.querySelector('label[for^="colorInput' + code + '-"]');
    const i = document.querySelector('input[id^="colorInput' + code + '-"]');
    return (l && (l.getAttribute('aria-label') || l.getAttribute('title') || l.textContent.trim())) ||
           (i && (i.getAttribute('aria-label') || i.getAttribute('title'))) || null;
  };
  const colours = stock ? Object.entries(stock).filter(([k, v]) => /^\d+$/.test(k) && v && Array.isArray(v.size)).map(([code, v]) => ({
    code, name: colourName(code),
    sizes: (v.size || []).map(z => ({size: z.label, sku: z.skuId, stock: +z.stockLevel, in_stock: +z.stockLevel > 0,
      price: +z.rawSalePrice || null, list_price: +z.rawListPrice || null}))
  })) : [];
  const compEl = document.querySelector('.compositionAndCare-composition .compositionAndCare-wrapper') ||
                 document.querySelector('.compositionAndCare-composition');
  const comp = compEl ? compEl.textContent.replace(/\s+/g, ' ').replace(/^Composition\s*/i, '').trim() : null;
  const NAT = /cotton|wool|linen|silk|cashmere|merino|hemp|lyocell|tencel|alpaca|mohair|yak|camel/i;
  const parts = comp ? [...comp.matchAll(/(\d{1,3})\s?%\s?([a-z][a-z \-]+?)(?=\d|,|;|$)/gi)].map(m => [+m[1], m[2].trim()]) : [];
  const nat = parts.length ? parts.filter(([, f]) => NAT.test(f)).reduce((a, [n]) => a + n, 0) : null;
  return JSON.stringify({
    url: location.href, title: document.title, name: p.name || null,
    brand: (p.brand && (p.brand.name || p.brand)) || ((document.title.split('|')[1] || '').trim() || null),
    price: o.price != null ? +o.price : null, currency: o.priceCurrency || null,
    availability: String(o.availability || '').replace('https://schema.org/', '') || null,
    image: Array.isArray(p.image) ? p.image[0] : (p.image || null),
    composition: comp, natural_pct: nat, colours,
    stock_found: !!stock
  });
})()

// asics_sizes.js (2026-10-08): ASICS CA (Magento 2) per-colour x per-size availability from a rendered PDP.
// Run via the iMac (VPS browser + curl are Akamai "Access Denied"; web_extract renders but has no stock):
//   scp -q asics_sizes.js sumeet@100.119.136.41:.hermes/
//   ssh sumeet@100.119.136.41 'cd ~/.hermes && costco-venv/bin/python mac_cdp_fetch.py asics_sizes.js <pdp-url>'
// WIDTH: ASICS sells each width as its OWN style/URL: men "<MODEL>" = D (standard), "<MODEL> WIDE" = 2E,
// "<MODEL> EXTRA WIDE" = 4E (women: B / WIDE = D / EXTRA WIDE = 2E). So "is 4E in stock in size X" =
// load the EXTRA WIDE style's PDP and read size X here. The PDP also prints "Extra Wide Fit" (width_text).
// Data: Magento swatch-renderer `jsonConfig` in <script type="text/x-magento-init">:
//   attributes{id:{code:'color'|'size'..., options:[{id,label,products:[simpleIds]}]}}
//   A size is available for a colour iff the two options share a simple-product id. Sizes whose
//   `products` list is empty are sold out in every colour. (`salable`, when present, is the same map
//   restricted to in-stock simples.) "6H" = US 6.5.
(() => {
  if (/Access Denied/i.test(document.title)) return {ready: true, blocked: true, title: document.title};
  const h1 = (document.querySelector('h1') || {}).innerText || '';
  let cfg = null;
  for (const s of document.querySelectorAll('script[type="text/x-magento-init"]')) {
    if (!/jsonConfig/.test(s.textContent)) continue;
    try {
      // several widgets carry a jsonConfig; keep the swatch one (has .attributes); may be a JSON string
      const walk = o => { if (!o || typeof o !== 'object' || cfg) return;
        if (o.jsonConfig) { let c = o.jsonConfig; if (typeof c === 'string') { try { c = JSON.parse(c); } catch (e) {} }
          if (c && c.attributes) { cfg = c; return; } }
        Object.values(o).forEach(walk); };
      walk(JSON.parse(s.textContent));
    } catch (e) {}
    if (cfg) break;
  }
  if (!h1 || !cfg || !cfg.attributes) return {ready: false, title: document.title, h1};
  const attrs = Object.entries(cfg.attributes).map(([id, a]) => ({id, code: a.code, label: a.label, options: a.options || []}));
  const col = attrs.find(a => /colou?r/i.test(a.code + a.label));
  const siz = attrs.find(a => /size/i.test(a.code + a.label));
  const salable = cfg.salable || null;
  const ok = (attrId, optId, pid) => !salable || !salable[attrId] || !salable[attrId][optId] || salable[attrId][optId].includes(pid);
  const matrix = (col ? col.options : [{id: 'all', label: 'all', products: null}]).map(c => ({
    colour: c.label, colour_id: c.id,
    sizes: siz.options.map(s => {
      const live = s.products.filter(p => (!c.products || c.products.includes(p)) && ok(siz.id, s.id, p));
      return {size: s.label.replace(/H$/, '.5'), in_stock: live.length > 0};
    })
  }));
  const t = document.body.innerText;
  const urlStyle = (location.pathname.match(/(\d{4}[a-z]\d{3})-(\d{3})/i) || []);
  return {ready: true, url: location.href, name: h1,
          price: (t.match(/\$\d{2,3}\.\d\d/) || [''])[0],
          width_text: (t.match(/(Extra Wide|Wide|Narrow|Standard) Fit/i) || [''])[0],
          stock_text: (t.match(/In stock|Out of stock/i) || [''])[0],
          url_colour_code: urlStyle[2] || null, size_attr: siz && siz.code, colour_attr: col && col.code,
          has_salable: !!salable, matrix};
})()

// lululemon_extract.js (2026-10-09): Lululemon Canada search -> PDP -> per-colour x per-size stock + fibre.
// The VPS gets GE401001 on everything (curl, web_extract, VPS browser), so run on the iMac:
//   scp -q lululemon_extract.js sumeet@100.119.136.41:.hermes/
//   ssh sumeet@100.119.136.41 'cd ~/.hermes && costco-venv/bin/python mac_cdp_fetch.py lululemon_extract.js \
//        "https://shop.lululemon.com/en-ca/search?Ntt=cotton%20t-shirt"  \
//        "https://shop.lululemon.com/en-ca/p/<slug>/<prod-id>"'
// One script, two page types (picked by URL):
//   /search or /c/  -> {kind:'search', links:[pdp urls]}   (anchors + __NEXT_DATA__ regex, deduped)
//   /p/             -> {kind:'pdp', name, image, colours:{<name>:{code, price, list, on_sale, in:[], out:[],
//                        materials:[{part, items:['100% Cotton']}], natural_pct_worst}}}
// No size filter in-page: the PDP redirect strips any #fragment/extra query (verified 2026-10-09). Filter in Python.
// FIBRE (2026-10-09): productSummary.productInfoByStyle.<STYLE>.colors.<colourCode>.materials[] = one entry
// per garment PART ({name:'Body', items:['100% Cotton']}, {name:'Collar and Cuff', items:['46% Cotton',...]}).
// Stored per colour, so read the exact colour. natural_pct_body = the Body/Main part; natural_pct_worst = min
// over parts (trim included). "100% cotton" marketing copy usually means the body only.
// Data: __NEXT_DATA__ walk for the first object with skus[] whose items carry `size`; each sku has
//   color.name, size, inseam (bottoms), available (bool), price.{listPrice,salePrice,onSale}.
// RATE LIMIT: Lululemon bans the home IP (GE401001) after ~20 PDP loads in 10 min. Keep <=15 loads per
// 10 min (mac_cdp_fetch already waits 20 s between URLs). Stop at the first {blocked:true}.
(async () => {
  const t = document.title || '';
  const body = document.body ? document.body.innerText : '';
  if (/GE401001|Access Denied/i.test(t + body.slice(0, 500))) return {ready: true, blocked: true, title: t};
  const nd = document.getElementById('__NEXT_DATA__');
  const path = location.pathname;
  if (/\/p\//.test(path)) {
    if (!nd) return {ready: false};
    let d; try { d = JSON.parse(nd.textContent); } catch (e) { return {ready: false}; }
    let prod = null, info = null; const seen = new Set();
    const walk = (o, depth) => {
      if (!o || typeof o !== 'object' || depth > 16 || seen.has(o)) return;
      seen.add(o);
      if (!prod && Array.isArray(o.skus) && o.skus.length && o.skus[0].size !== undefined) prod = o;
      if (!info && o.productInfoByStyle && typeof o.productInfoByStyle === 'object') info = o.productInfoByStyle;
      for (const k in o) walk(o[k], depth + 1);
    };
    try { walk(d, 0); } catch (e) { return {ready: false, err: String(e).slice(0, 100)}; }
    if (!prod) return {ready: false, why: 'noskus'};
    const NAT = /cotton|wool|linen|silk|cashmere|merino|hemp|lyocell|tencel|alpaca|mohair/i;
    const matByCode = {};
    try { Object.values(info || {}).forEach(st => Object.entries(st.colors || {}).forEach(([code, c]) => {
      if (!matByCode[code] && Array.isArray(c.materials)) matByCode[code] = c.materials.map(m => ({
        part: m.name || m.title || m.label || m.type || null,
        items: (m.items || []).filter(x => typeof x === 'string')}));
    })); } catch (e) {}
    const natPct = mats => { if (!mats || !mats.length) return null;
      const v = mats.map(m => m.items.reduce((a, x) => { const n = x.match(/(\d{1,3})%\s*(.+)/); return a + (n && NAT.test(n[2]) && !/recycled poly/i.test(n[2]) ? +n[1] : 0); }, 0));
      return Math.min(...v); };
    const natBody = mats => { if (!mats || !mats.length) return null;
      const b = mats.find(m => /body|main|shell|self/i.test(m.part || '')) || mats[0];
      return natPct([b]); };
    const colours = {};
    for (const s of prod.skus) {
      const c = (s.color && s.color.name) || '?';
      const pr = s.price || {};
      const p = pr.onSale ? +pr.salePrice : +pr.listPrice;
      const code = s.color && s.color.code;
      const e = colours[c] = colours[c] || {code: code || null, price: p || null, list: +pr.listPrice || null, on_sale: !!pr.onSale,
        in: [], out: [], materials: matByCode[code] || null, natural_pct_worst: natPct(matByCode[code]), natural_pct_body: natBody(matByCode[code])};
      if (p && (!e.price || p < e.price)) e.price = p;
      const label = String(s.size) + (s.inseam ? '/' + String(s.inseam).replace('"', 'in') : '');
      const b = s.available ? e.in : e.out;
      if (!b.includes(label)) b.push(label);
    }
    return {ready: true, kind: 'pdp', url: location.href.split('#')[0],
            name: ((document.querySelector('h1') || {}).innerText || '').trim(), currency: 'CAD',
            image: (document.querySelector('meta[property="og:image"]') || {}).content || null,
            n_skus: prod.skus.length, materials_found: Object.keys(matByCode).length, colours};
  }
  // search / category page
  window.scrollTo(0, document.body.scrollHeight);
  await new Promise(r => setTimeout(r, 1500));
  const a = [...document.querySelectorAll('a[href*="/p/"]')].map(x => x.href.split('?')[0].split('#')[0]);
  const fromND = nd ? (nd.textContent.match(/\/en-ca\/p\/[a-z0-9\-]+\/[A-Za-z0-9_]{5,14}/g) || []).map(p => 'https://shop.lululemon.com' + p) : [];
  const links = [...new Set([...a, ...fromND])].filter(u => /\/p\//.test(u));
  if (links.length < 3) return {ready: false, n: links.length, title: t};
  return {ready: true, kind: 'search', title: t, n: links.length, links: links.slice(0, 60)};
})()

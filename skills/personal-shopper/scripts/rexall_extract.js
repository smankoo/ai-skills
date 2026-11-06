// rexall_extract.js — Rexall (shop.rexall.ca = Instacart Storefront Pro), run via the iMac CDP helper.
// USAGE (from VPS):
//   scp -q rexall_extract.js sumeet@100.119.136.41:.hermes/
//   ssh -o BatchMode=yes sumeet@100.119.136.41 'cd ~/.hermes && costco-venv/bin/python mac_cdp_fetch.py rexall_extract.js \
//      "https://shop.rexall.ca/store/rexall/s?k=whey%20protein" \
//      "https://shop.rexall.ca/store/rexall/products/24831268-la-roche-posay-cicaplast-mains-barrier-repairing-hand-cream-50-ml"'
// Search URL -> up to 20 items; PDP URL -> that item. Each item: name, size, price, was (reg.), sale label,
// available, stockLevel, image, url. Uses the site's own persisted-query GraphQL (same-origin fetch);
// the VPS gets Imperva 403 on shop.rexall.ca for everything except web_extract of PDPs.
// Hashes verified 2026-10-08. If a call returns PersistedQueryNotFound, reload a search page with
// DevTools/perf entries and copy the new sha256Hash for that operationName.
(async () => {
  if (!/shop\.rexall\.ca/.test(location.host) || !document.body || document.body.innerText.length < 300) return {ready:false};
  const H = {Items:'8fe60a2c4c74b994076e8fc97883141aec582e7f6e2402d82c9902772432f183',
             ItemPricesQuery:'b9bcf36721a5f43a2c356d42d16ef002ed24941034a3dad53485b0f627aa2450',
             SearchResultsPlacements:'8cd689fec18fd7db71b4710b1f51b81699562a3cee9058fd7c0bf3719a66c3e1'};
  const q = (op, vars) => fetch(`/graphql?operationName=${op}&variables=${encodeURIComponent(JSON.stringify(vars))}&extensions=${encodeURIComponent(JSON.stringify({persistedQuery:{version:1, sha256Hash:H[op]}}))}`, {headers:{accept:'application/json'}}).then(r => r.json());
  // Session context (shop / zone / postal / retailer-location) from the page's own GraphQL calls.
  const ents = performance.getEntriesByType('resource').map(e => decodeURIComponent(e.name)).filter(u => /\/graphql\?/.test(u));
  const pick = re => { for (const u of ents) { const m = u.match(re); if (m) return m[1]; } return null; };
  const shopId = pick(/"shopId":"(\d+)"/), zoneId = pick(/"zoneId":"(\d+)"/), postalCode = pick(/"postalCode":"([A-Z0-9]+)"/);
  const locId = pick(/items_(\d+)-\d+/) || pick(/"retailerLocationId":"(\d+)"/);
  if (!shopId || !zoneId || !locId) return {ready:false, note:'context not loaded yet', shopId, zoneId, locId};
  const base = {shopId, zoneId, postalCode};
  let ids = [];
  const pm = location.pathname.match(/\/products\/(\d+)/);
  const kw = new URLSearchParams(location.search).get('k') || (location.pathname.match(/search_v3\/([^/?]+)/) || [])[1];
  if (pm) ids = [`items_${locId}-${pm[1]}`];
  else if (kw) {
    const s = await q('SearchResultsPlacements', {action:null, query: decodeURIComponent(kw), pageViewId: crypto.randomUUID(), elevatedProductId:null, searchSource:'search', filters:[], disableReformulation:false, disableLlm:false, forceInspiration:false, orderBy:'bestMatch', clusterId:null, includeDebugInfo:false, clusteringStrategy:null, contentManagementSearchParams:{itemGridColumnCount:5}, ...base, first:20});
    const seen = new Set();
    (function walk(o) { if (!o) return; if (typeof o === 'string') { if (/^items_\d+-\d+$/.test(o)) seen.add(o); return; }
      if (typeof o === 'object') for (const k in o) walk(o[k]); })(s.data);
    ids = [...seen].slice(0, 20);
  } else return {ready:false, note:'not a search or product URL'};
  if (!ids.length) return {ready:true, n:0, items:[], ctx: base};
  const [it, pr] = await Promise.all([q('Items', {ids, ...base}), q('ItemPricesQuery', {ids, ...base})]);
  const P = {}; for (const p of (pr.data && pr.data.itemPrices) || []) P[p.id] = p;
  const items = ((it.data && it.data.items) || []).map(x => {
    const c = ((P[x.id] || {}).viewSection || {}).itemCard || {}, b = ((P[x.id] || {}).viewSection || {}).badge || {};
    const vs = x.viewSection || {}, av = x.availability || {};
    return {id: x.id, productId: x.productId, brand: x.brandName, name: x.name, size: x.size,
      price: c.priceString || null, was: c.plainFullPriceString || null, unit_price: c.pricePerUnitString || null,
      sale: b.offerLabelString || null, available: av.available, stockLevel: av.stockLevel,
      variants: ((x.variantGroup || {}).viewSection || {}).optionsSummaryString || null,
      image: (vs.itemImage || {}).url || null,
      url: 'https://shop.rexall.ca/store/rexall/products/' + (x.evergreenUrl || x.productId)};
  });
  return {ready:true, ctx: {...base, retailerLocationId: locId}, n: items.length, items};
})()

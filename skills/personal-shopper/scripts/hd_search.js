// hd_search.js — Home Depot CA search on the iMac (VPS gets Akamai 403 on /search and /api/search).
// Usage (iMac): costco-venv/bin/python mac_cdp_fetch.py hd_search.js "https://www.homedepot.ca/search?q=<query>"
// The tab is on www.homedepot.ca, so it same-origin fetches the page's own API:
//   GET /api/search/v1/search?q=<q>&page=1&pageSize=40&lang=en  (verified 2026-10-12)
// Returns {ready, q, n, keys, items:[{id,name,brand,url,price,was,rating,image}]}; store stock/price per
// store come from the VPS-open productsvc API (homedepot_extract.py <id> ...).
(() => {
  if (/Access Denied/i.test(document.title)) return {ready:true, blocked:true, title:document.title};
  if (!window.__hdS) {
    window.__hdS = {state:'pending'};
    const q = new URLSearchParams(location.search).get('q') || '';
    fetch('/api/search/v1/search?q='+encodeURIComponent(q)+'&page=1&pageSize=40&lang=en',
          {headers:{'Accept':'application/json'}, credentials:'include'})
      .then(r => r.json().then(j => { window.__hdS = {state:'ok', status:r.status, q, j}; }))
      .catch(e => { window.__hdS = {state:'err', err:String(e)}; });
    return {ready:false};
  }
  const S = window.__hdS;
  if (S.state === 'pending') return {ready:false};
  if (S.state === 'err') return {ready:true, err:S.err};
  try {
    const j = S.j || {};
    // find the product array wherever it lives
    let arr = j.products || (j.searchResult && j.searchResult.products) || null;
    if (!arr) { for (const k of Object.keys(j)) { if (Array.isArray(j[k]) && j[k].length && j[k][0] && (j[k][0].code||j[k][0].productId)) { arr=j[k]; break; } } }
    arr = arr || [];
    const num = v => (v && typeof v==='object') ? (v.value ?? null) : (v ?? null);
    const items = arr.map(p => {
      const pr = p.pricing || {};
      return {
        id: p.code || null,
        name: ((p.brand ? p.brand+' ' : '') + (p.name||'')).trim() || null,
        brand: p.brand || null,
        model: p.modelNumber || null,
        url: p.url ? new URL(p.url, location.origin).href : null,
        price: num(pr.displayPrice),
        was: num(pr.wasprice),
        pricing_store: pr.storeId || null,     // the iMac profile's store, NOT Burlington
        rating: p.productRating ? p.productRating.averageRating : null,
        reviews: p.productRating ? p.productRating.totalReviews : null,
        image: p.imageUrl || null,
        online_stock: p.stock ? p.stock.stockLevel : null,
        store_stock: p.storeStock ? p.storeStock.stockLevel : null,
      };
    });
    return {ready:true, status:S.status, q:S.q, keys:Object.keys(j).slice(0,20),
            n:items.length, items};
  } catch(e) { return {ready:true, err:String(e)}; }
})()

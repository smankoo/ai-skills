// Costco.ca search via its own JSON API (gdx-api.costco.com/catalog/search/api/v1/search), verified 2026-10-08.
// Runs in an iMac CDP tab on www.costco.ca (the API allows Origin https://www.costco.ca; from the VPS it is
// behind the same Akamai wall as the site). Load the normal search URL and this extractor re-issues the
// API call with the keyword from the URL, returning clean JSON instead of scraping tiles:
//   ssh ... 'cd ~/.hermes && costco-venv/bin/python mac_cdp_fetch.py costco_search_api.js \
//            "https://www.costco.ca/CatalogSearch?keyword=paper%20towels"'
// Optional URL params read by this extractor: &cx_size=24 &cx_offset=0 &cx_raw=1 (return first raw result too).
// Headers: client_id CABC, locale en-CA, searchResultProvider GRS, and client-identifier = the public app key the
// site's own JS sends for the search service (captured 2026-10-08; a random UUID gets HTTP 401). If it starts
// 401-ing, re-capture with cdp_netcap.py and pass &cx_cid=<uuid>. credentials:'include' fails CORS; use 'omit'. warehouseId / shipToPostal / deliveryLocations come from the page's
// stored location; the defaults below are what the iMac's tab sent (an Oakville-area postal), so
// prices = online prices, warehouse stock = that warehouse.
(async () => {
  const p = new URLSearchParams(location.search);
  const q = p.get('keyword');
  if (!q) return { ready: true, error: 'open a /CatalogSearch?keyword=<q> URL' };
  if (/Access Denied/i.test(document.title)) return { ready: true, blocked: document.title };
  const size = +(p.get('cx_size') || 24), offset = +(p.get('cx_offset') || 0);
  // reuse the page's own request body if we can see it in resource timing? (not exposed) -> rebuild it
  const body = {
    visitorId: (crypto.randomUUID ? crypto.randomUUID() : String(Date.now())).replace(/-/g, ''),
    query: q, pageSize: size, offset, orderBy: null, searchMode: 'page', personalizationEnabled: false,
    warehouseId: p.get('cx_wh') || '531-wh', shipToPostal: p.get('cx_postal') || 'L6M 2P7', shipToState: 'ON',
    deliveryLocations: ['1436-bd', '531-wh', '559-dz', '559-wm', '792-wm', '894_0-cwt', '894_0-edi', '894_0-membership',
      '894_0-mpt', '894_0-otw', '894_0-spc', '894_1-edi', '894_1-mpt', '946-dz', '946-wm', '9894-wcs', '993-wm'],
    filterBy: p.get('cx_all') ? [] : ['HIDE_OUT_OF_STOCK'], pageCategories: []
  };
  let r, j;
  try {
    r = await fetch('https://gdx-api.costco.com/catalog/search/api/v1/search', {
      method: 'POST', credentials: 'omit',
      headers: { 'Content-Type': 'application/json', client_id: 'CABC', locale: 'en-CA', searchResultProvider: 'GRS',
                 'client-identifier': p.get('cx_cid') || '168287ea-1201-45f6-9b45-5bbea49f8ee7' },
      body: JSON.stringify(body)
    });
    j = await r.json();
  } catch (e) { return { ready: false, err: String(e).slice(0, 150) }; }
  const sr = j.searchResult || {};
  const A = (prod, k) => { const a = (prod.attributes || {})[k]; return a ? (a.text && a.text.length ? a.text : a.numbers) : null; };
  const results = (sr.results || []).map(x => {
    const pr = x.product || {};
    const v0 = (pr.variants || [])[0] || {};
    const pi = v0.priceInfo || pr.priceInfo || {};
    return {
      id: x.id, item: v0.id || null, title: pr.title, brand: (pr.brands || [])[0] || null,
      url: pr.uri, price: pi.price != null ? pi.price : null, original_price: pi.originalPrice != null ? pi.originalPrice : null,
      currency: pi.currencyCode || null,
      rating: pr.rating ? Math.round(pr.rating.averageRating * 100) / 100 : null, reviews: pr.rating ? pr.rating.ratingCount : null,
      image: (A(pr, 'primary_image') || [])[0] || null, programs: A(pr, 'program_types'),
      member_only: (A(pr, 'member_only') || [])[0] === 1, buyable: (A(pr, 'buyable') || [])[0] === 1,
      category: (pr.categories || []).slice(-1)[0] || null,
      availability: v0.availability || pr.availability || null,
      variant_attr_keys: Object.keys(v0.attributes || {}).slice(0, 40)
    };
  });
  const out = { ready: true, status: r.status, query: q, total: sr.totalSize != null ? sr.totalSize : null,
                n: results.length, results, top_keys: Object.keys(sr) };
  if (p.get('cx_raw')) out.raw0 = JSON.stringify((sr.results || [])[0]).slice(0, 12000);
  return out;
})()

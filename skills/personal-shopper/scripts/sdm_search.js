// sdm_extract.js — Shoppers Drug Mart (iMac CDP). Works on /search?text=… and /p/BB_… pages.
// Reads server-rendered __NEXT_DATA__ (no DOM scraping). Returns {ready:true, kind, ...}.
(async () => {
  const el = document.getElementById('__NEXT_DATA__');
  if (!el) return {ready: false, title: document.title};
  const nd = JSON.parse(el.textContent), pp = nd.props.pageProps;
  const vd = pp.viewDefinition;
  if (vd && vd.code && vd.jsonLd) {               // PDP
    const ld = vd.jsonLd, off = ld.offers || {};
    return {ready: true, kind: 'pdp', title: document.title, code: vd.code, brand: vd.brandName, name: vd.name,
      price: vd.price && vd.price.value, effective_price: vd.effectivePrice && vd.effectivePrice.value,
      on_sale: vd.isOnSale, sale_ends: vd.isOnSale ? (vd.effectivePrice || {}).endDate : null,
      size: vd.size, out_of_stock: vd.isOutOfStock, stock_level: (vd.stock || {}).stockLevel,
      purchasable: vd.purchasable, availability: off.availability, pco_points: vd.baseOptimumPoints,
      promos: (vd.optimumPromotions || []).concat(vd.potentialPromotions || []).map(p => p.description || p.title || JSON.stringify(p).slice(0, 160)),
      variants: (vd.variantOptions || vd.variants || []).length || undefined,
      image: (ld.image || [])[0], url: vd.canonicalUrl};
  }
  const tiles = [];
  (function walk(o) {
    if (!o || typeof o !== 'object') return;
    if (Array.isArray(o.productTiles)) tiles.push(...o.productTiles);
    for (const k in o) walk(o[k]);
  })(pp);
  if (!tiles.length) return {ready: false, title: document.title, note: 'no productTiles'};
  return {ready: true, kind: 'search', title: document.title, n: tiles.length,
    items: tiles.map(t => ({id: t.productId, brand: t.brand, title: t.title, price: t.pricing && t.pricing.price,
      was: t.pricing && (t.pricing.wasPrice || t.pricing.regularPrice || null), pricing: t.pricing,
      stock: (t.inventoryIndicator || {}).indicatorId, deal: t.pcoDeal || t.textBadge || '', sponsored: t.isSponsored,
      url: 'https://www.shoppersdrugmart.ca' + (t.link || '').split('&source')[0],
      image: ((t.productImage || [])[0] || {}).imageUrl}))};
})()

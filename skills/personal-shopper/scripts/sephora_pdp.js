// sephora_pdp.js — Sephora CA per-variant price/stock via same-origin product API (iMac, mac_cdp_fetch.py).
// Open: https://www.sephora.com/ca/en/product/<slug>-P<id>   (optionally ?skuId=<n>)
// The page's own origin calls /api/v3/catalog/products/<PID>?showContent=true&includeRegionsMap=true&loc=en-CA&countryCode=CA
// which is Akamai-403 from the VPS but answers inside an iMac tab. Returns
// {ready, pid, name, brand, rating, reviews, ingredients, image, variants:[{sku, label, price, list, oos, limited, online_only, image}]}
(async () => {
  const m = location.pathname.match(/-(P\d+)/);
  if (!m) return {ready: false, why: 'no PID in url'};
  if (/access denied/i.test(document.title)) return {ready: false, wall: document.title};
  const pid = m[1];
  let j;
  try {
    const r = await fetch(`/api/v3/catalog/products/${pid}?showContent=true&includeRegionsMap=true&loc=en-CA&countryCode=CA`,
      {headers: {accept: 'application/json'}, credentials: 'include'});
    if (!r.ok) return {ready: false, status: r.status};
    j = await r.json();
  } catch (e) { return {ready: false, err: String(e)}; }
  const strip = s => (s || '').replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
  const pick = s => s && {
    sku: s.skuId, label: [s.variationType, s.variationValue, s.variationDesc, s.size].filter(Boolean).join(' | '),
    price: s.salePrice || s.listPrice, list: s.listPrice, sale: s.salePrice || null,
    oos: !!s.isOutOfStock, limited: !!(s.isOnlyFewLeft), online_only: !!s.isOnlineOnly,
    ingredients: strip(s.ingredientDesc).slice(0, 1500) || null,
    image: s.skuImages && (s.skuImages.image450 || s.skuImages.image250 || s.skuImages.imageUrl) || null,
  };
  const cur = j.currentSku || {};
  const all = [cur, ...(j.regularChildSkus || []), ...(j.onSaleChildSkus || [])];
  const seen = new Set(), variants = [];
  for (const s of all) { if (s && s.skuId && !seen.has(s.skuId)) { seen.add(s.skuId); variants.push(pick(s)); } }
  const pi = j.productDetails || {};
  const ing = variants.length ? variants[0].ingredients : null;
  variants.forEach(v => { if (v.ingredients === ing) delete v.ingredients; });
  return {ready: true, pid, name: pi.displayName, brand: pi.brand && pi.brand.displayName,
    rating: pi.rating, reviews: pi.reviews, ingredients: ing,
    image: variants[0] && variants[0].image ? (variants[0].image.startsWith('http') ? variants[0].image : 'https://www.sephora.com' + variants[0].image) : null,
    n_variants: variants.length, variants: variants.slice(0, 40), url: location.href.split('?')[0]};
})()

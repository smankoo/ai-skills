// childrensplace_pdp.js (2026-10-08): The Children's Place CA PDP extractor for a RENDERED tab.
// Usage (VPS browser, own session):  goto_url(pdp); wait_for_load(); sleep 6; js(open(this).read())
// Also works as a mac_cdp_fetch.py extractor (returns {ready:true,...}).
// Why: web_extract now returns a ~700-char stub for TCP PDPs (title + description only; no price,
// no sizes), so childrensplace_extract.py gets sizes:[] — use the VPS browser instead (no wall there).
// Data: JSON-LD ProductGroup (name, per-COLOUR price+availability), DOM size labels
// `label.size-field` (sold-out size has class `item-disabled-option`), "Sale Price:/Original Price:" text,
// "FABRICATION:" line = composition.
(() => {
  const s = [...document.querySelectorAll('script[type="application/ld+json"]')].map(x => x.textContent)
    .find(t => /ProductGroup/.test(t));
  const labels = [...document.querySelectorAll('label.size-field')];
  if (!s || !labels.length) return {ready: false, title: document.title};
  let j = JSON.parse(s); if (Array.isArray(j)) j = j[0];
  const t = document.body.innerText;
  const num = re => { const m = t.match(re); return m ? parseFloat(m[1]) : null; };
  const colour = ((t.match(/Color:\s*([^\n]+)/) || [])[1] || '').trim();
  return {
    ready: true, url: location.href, name: j.name, item_no: (t.match(/Item #:\s*(\S+)/) || [])[1] || j.productId,
    sale_price: num(/Sale Price:\s*\$(\d+\.\d\d)/), original_price: num(/Original Price:\s*\$(\d+\.\d\d)/),
    currency: ((j.offers || {}).priceCurrency) || 'CAD', selected_colour: colour,
    composition: ((t.match(/FABRICATION:\s*([^\n]+)/) || [])[1] || '').trim(),
    sizes: labels.map(l => ({size: l.innerText.trim(), in_stock: !/item-disabled-option/.test(l.className)})),
    colours: (j.hasVariant || []).map(v => ({sku: v.sku, colour: v.color, price: (v.offers || {}).price,
      availability: String((v.offers || {}).availability || '').split('/').pop()})),
    image: Array.isArray(j.image) ? j.image[0] : j.image,
  };
})()

// michaels_pdp.js — Michaels Canada (canada.michaels.com) PDP + per-store stock on the iMac (verified 2026-10-13).
// VPS: Akamai 403 on canada.michaels.com, www.michaels.com/api/* and locationsca.michaels.com (curl + web_extract).
// Usage (iMac): costco-venv/bin/python mac_cdp_fetch.py michaels_pdp.js "https://canada.michaels.com/product/<slug>-<sku>[#store=4939]"
// Burlington stores: 4917, 4939 (locationsca.michaels.com/on/burlington/<id>). Default 4917; pick another with #store=<id>.
// Method: JSON-LD ProductGroup -> hasVariant[] (sku, colour, image, price; NB variant offers say "USD", the
//   top-level Offer says CAD and is the price shown). Then same-origin fetch of the page's own API:
//   GET www.michaels.com/api/product/v2/sub-skus?source=pdpPage&orginSkuNumber=<sku>&michaelsStoreId=<store>&skuNumbers=<a,b,..>&fields=inventory
//   -> per sku: inventoryMcu.availableQuantity (online/DC), inventoryStorePickUp (that store's qty), promotionMpe offers.
//   GET www.michaels.com/api/store-locator/store?michaelsStoreId=<id> -> store name/address.
// Sale/reg on the DOM: .product-sales-price / .price-standard ("Reg.$3.99").
(() => { try {
  if (document.readyState !== 'complete') return {ready:false};
  if (/access denied/i.test(document.title)) return {ready:true, blocked:true, title:document.title};
  if (window.__MK) return window.__MK.done ? window.__MK : {ready:false};
  const lds = [];
  for (const s of document.querySelectorAll('script[type="application/ld+json"]')) {
    try { const j = JSON.parse(s.textContent); (Array.isArray(j)?j:(j['@graph']||[j])).forEach(x=>lds.push(x)); } catch(e){}
  }
  const pg = lds.find(x => /Product/.test([].concat(x['@type']).join(',')));
  if (!pg) return (window.__mkN=(window.__mkN||0)+1) > 8 ? {ready:true, err:'no Product JSON-LD', title:document.title} : {ready:false};
  window.__MK = {ready:false};
  const store = ((location.hash.match(/store=(\d+)/)||[])[1]) || '4917';
  const sku = (location.pathname.match(/-(\d{6,})$/)||[])[1] || pg.sku;
  const vars = [].concat(pg.hasVariant || [pg]);
  const skus = [...new Set([sku].concat(vars.map(v=>v.sku)).filter(Boolean))];
  const tx = s => { const e=document.querySelector(s); return e ? e.innerText.replace(/\s+/g,' ').trim() : null; };
  const num = t => { const m=(t||'').match(/\$\s?([\d,]+\.\d\d)/); return m ? parseFloat(m[1].replace(/,/g,'')) : null; };
  const top = [].concat(pg.offers||[])[0] || {};
  const R = {ready:true, done:true, store_id:store, sku, name:pg.name, brand:pg.brand && (pg.brand.name||pg.brand),
    price: top.price!=null ? Number(top.price) : num(tx('.product-sales-price')), currency: top.priceCurrency || 'CAD',
    was: num(tx('.price-standard')), availability:(top.availability||'').replace(/.*\//,''),
    description: (pg.description||'').slice(0,400), image: [].concat((vars.find(v=>v.sku==sku)||vars[0]||{}).image||pg.image||[])[0] || null};
  const api = 'https://www.michaels.com/api';
  Promise.all([
    fetch(`${api}/product/v2/sub-skus?source=pdpPage&orginSkuNumber=${sku}&michaelsStoreId=${store}&skuNumbers=${skus.join(',')}&fields=inventory`, {credentials:'include'}).then(r=>r.json()).catch(e=>({err:String(e)})),
    fetch(`${api}/store-locator/store?michaelsStoreId=${store}`, {credentials:'include'}).then(r=>r.json()).catch(e=>({err:String(e)}))
  ]).then(([inv, st]) => {
    const byS = {}; if (Array.isArray(inv)) inv.forEach(x => byS[x.skuNumber] = x);
    R.store = st && st.michaels_store_name ? `${st.michaels_store_name}, ${st.address}, ${st.city}` : null;
    R.promos = ((byS[sku]||{}).promotionMpe||{offer:[]}).offer.map(o=>o.calloutMessage).filter(Boolean).slice(0,3);
    R.variants = vars.map(v => { const i = byS[v.sku] || {}; const s = i.inventoryStorePickUp || i.inventoryStore || {}; const m = i.inventoryMcu || {};
      return {sku:v.sku, colour:v.color || (v.name||'').replace(pg.name,'').replace(/^[,\s:-]+/,'') || null,
        image:[].concat(v.image||[])[0]||null, online_qty:m.availableQuantity ?? null, online_in_stock:m.inStock ?? null,
        store_qty: s.availableQuantity ?? null, store_in_stock: s.inStock ?? null}; });
    if (!Array.isArray(inv)) R.inventory_err = JSON.stringify(inv).slice(0,300);
    window.__MK = R;
  });
  return {ready:false};
} catch(e) { return {ready:true, err:String(e)}; } })()

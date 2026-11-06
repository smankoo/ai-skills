// Metro.ca search-tile extractor. Run it in the VPS browser (browser_exec) on a metro.ca tab.
// Verified 2026-10-08. plain curl = 403, the browser passes.
// Usage from browser_exec (Python):
//   goto_url("https://www.metro.ca/en/online-grocery/search?filter=milk"); wait_for_load()
//   # one-time per browser profile: set the shopping store (223 = Metro Millcroft, 2010 Appleby Line Burlington)
//   csrf = js("(document.querySelector('meta[name=_csrf]')||{}).content||(document.querySelector('input[name=_csrf]')||{}).value||''")
//   js("fetch('/stores/my-store/223',{method:'POST',credentials:'include',body:new URLSearchParams({userConfirmation:'true',lang:'en'}),headers:{'X-CSRF-TOKEN':'%s','X-Requested-With':'XMLHttpRequest'}}).then(r=>r.status)" % csrf)
//   goto_url("https://www.metro.ca/en/online-grocery/search?filter=" + urllib.parse.quote(q)); wait_for_load()
//   print(js(open('metro_search.js').read()))
// Returns {store, items:[{code,brand,name,size,price,regular,unit_price,sale,url,image}]}
(() => {
  const m = document.body.innerText.match(/\n([^\n]*)\nChange store/);
  const items = [...document.querySelectorAll('.default-product-tile[data-product-code]')].slice(0, 24).map(el => {
    const q = s => { const e = el.querySelector(s); return e ? e.innerText.replace(/\s+/g, ' ').trim() : null; };
    const img = el.querySelector('picture img');
    return {
      code: el.dataset.productCode, brand: el.dataset.productBrand || null, name: el.dataset.productName,
      size: q('.head__unit-details'),
      price: q('.pricing__sale-price'),                              // current price ("$4.99 ea.", or "$3.29 /lb.")
      regular: (q('.pricing__before-price') || '').replace(/^Regular price\s*/, '') || null, // present only when on sale
      unit_price: q('.pricing__secondary-price'),
      sale: !!el.querySelector('.promo-price'),
      inactive: el.dataset.isInactive === 'true',                     // the only availability flag on tiles
      url: (el.querySelector('a.product-details-link') || {}).href || null,
      image: img ? img.src : null,
    };
  });
  return { ready: items.length > 0, store: m ? m[1].trim() : null, items };
})()

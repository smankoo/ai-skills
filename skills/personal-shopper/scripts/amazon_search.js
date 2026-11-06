// Amazon.ca search-results extractor (verified 2026-10-08). Run in a tab on https://www.amazon.ca/s?k=<query>.
// Sponsored tiles (.puis-sponsored-label-text / "Sponsored" label / AdHolder) are dropped and counted.
// Returns {ready, query, n_total, n_sponsored, results:[{asin, url, title, price, list_price, unit_price,
//          rating, reviews, prime, delivery, fastest, badge, coupon}]}
(() => {
  const tiles = [...document.querySelectorAll('div[data-component-type="s-search-result"]')];
  if (!tiles.length) {
    const b = (document.body && document.body.innerText || '').slice(0, 300);
    return { ready: /No results|captcha|Enter the characters|Sorry/i.test(b), n_total: 0, page_title: document.title, head: b };
  }
  const isSp = e => !!(e.querySelector('.puis-sponsored-label-text, .s-sponsored-label-text, [aria-label="Sponsored"], a[href*="/sspa/click"]') || e.classList.contains('AdHolder'));
  const txt = (e, s) => { const x = e.querySelector(s); return x ? x.innerText.replace(/\s+/g, ' ').trim() : null; };
  const out = [];
  let sp = 0;
  for (const e of tiles) {
    if (!e.dataset.asin) continue;
    if (isSp(e)) { sp++; continue; }
    const asin = e.dataset.asin;
    const tr = e.querySelector('[data-cy="title-recipe"]');
    // Title: the h2 is sometimes ONLY the brand (electronics/apparel); join brand row + h2 when they differ.
    const h2s = tr ? [...tr.querySelectorAll('h2')].map(h => h.innerText.trim()) : [];
    let title = h2s.join(' ').trim() || (e.querySelector('h2') || {}).innerText || null;
    const h2a = e.querySelector('h2[aria-label]');
    if (h2a && h2a.getAttribute('aria-label').length > (title || '').length) title = h2a.getAttribute('aria-label').replace(/^Sponsored Ad - /, '');
    const pr = e.querySelector('[data-cy="price-recipe"]');
    const prices = pr ? [...pr.querySelectorAll('.a-price:not(.a-text-price) .a-offscreen')].map(x => x.textContent.trim()) : [];
    const strikeEl = pr ? pr.querySelector('.a-price[data-a-strike="true"]') : null;
    const list = strikeEl ? (strikeEl.querySelector('.a-offscreen') || {}).textContent || null : null;
    const list_kind = strikeEl ? ((strikeEl.parentElement.innerText.match(/^(Was|List|Typical)/) || [])[1] || 'strike') : null;
    const prText = pr ? pr.innerText.replace(/\s+/g, ' ') : '';
    const um = prText.match(/\(\s*\$[\d,.]+\s*\$?([\d,.]+)?\s*\/\s*([^)]+)\)/) || prText.match(/(\$[\d,.]+\/[a-z0-9 ]+)\)/i);
    const unit = (prText.match(/\$[\d,.]+\/\s*[A-Za-z0-9 ]+?(?=\))/) || [])[0] || null;
    const rb = e.querySelector('[data-cy="reviews-block"]');
    const ratingLbl = rb ? ([...rb.querySelectorAll('[aria-label]')].map(x => x.getAttribute('aria-label')).find(a => /out of 5/.test(a)) || (rb.querySelector('.a-icon-alt') || {}).textContent || null) : null;
    const revLbl = rb ? [...rb.querySelectorAll('[aria-label]')].map(x => x.getAttribute('aria-label')).find(a => /ratings?$/.test(a)) : null;
    const del = txt(e, '[data-cy="delivery-recipe"]');
    const moreBuying = /No featured offers|See options|other buying options/i.test(prText + ' ' + (e.innerText || ''));
    out.push({
      asin, url: 'https://www.amazon.ca/dp/' + asin, title,
      price: prices[0] || null, list_price: list, list_kind, unit_price: unit,
      rating: ratingLbl ? parseFloat(ratingLbl) : null,
      reviews: revLbl ? parseInt(revLbl.replace(/[^\d]/g, ''), 10) : (rb ? (rb.innerText.match(/\(([\d.,K]+)\)/) || [])[1] || null : null),
      prime: !!e.querySelector('i.a-icon-prime, [aria-label="Amazon Prime"]') || /\bPrime\b/.test(del || ''),
      delivery: del, no_featured_offer: !prices.length && moreBuying,
      badge: txt(e, '[data-cy="s-pc-faceout-badge"], .a-badge-text'),
      coupon: txt(e, '.s-coupon-unclipped, [data-component-type="s-coupon-component"]')
    });
  }
  const q = new URLSearchParams(location.search).get('k');
  return { ready: true, query: q, n_total: tiles.length, n_sponsored: sp, n_organic: out.length, results: out };
})()

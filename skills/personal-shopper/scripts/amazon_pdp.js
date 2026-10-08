// Amazon.ca product-page extractor (verified 2026-10-08). Run in a tab on https://www.amazon.ca/dp/<ASIN>.
// Returns {ready:true, asin, title, price, list_price, unit_price, seller_line, ships_from, sold_by,
//          amazon_sold, import_fees, availability, only_left, delivery, fastest, coupon, sns_price,
//          rating, reviews, image, variants:{dims, by_asin:{asin:[dim values]}}, ...}
// Read-only: it never clicks anything. Personal data (the "Deliver to <name>" line) is not returned.
(async () => {
  const $ = s => document.querySelector(s);
  const T = s => { const e = $(s); return e ? e.innerText.replace(/\s+/g, ' ').trim() : null; };
  const money = s => { const m = (s || '').match(/\$\s?([\d,]+\.\d{2})/); return m ? parseFloat(m[1].replace(/,/g, '')) : null; };
  const offs = root => root ? [...root.querySelectorAll('.a-price .a-offscreen')].map(e => e.textContent.trim()).filter(x => /\$/.test(x)) : [];
  const title = T('#productTitle');
  if (!title) {
    const b = (document.body && document.body.innerText || '').slice(0, 300);
    return { ready: /Sorry|captcha|Enter the characters|Page Not Found|looking for something/i.test(document.title + b), blocked_or_404: true, page_title: document.title, head: b };
  }
  const asin = ($('#ASIN') || {}).value || (location.pathname.match(/\/dp\/([A-Z0-9]{10})/) || [])[1] || null;

  // ---- price: priceToPay inside the core price block, then fallbacks
  const coreRoot = $('#corePrice_feature_div') || $('#corePriceDisplay_desktop_feature_div') || $('#apex_desktop');
  let priceTxt = null;
  for (const sel of ['#corePriceDisplay_desktop_feature_div .priceToPay .a-offscreen', '#corePrice_feature_div .a-price .a-offscreen',
                     '#apex_desktop .priceToPay .a-offscreen', '#apex_desktop .a-price .a-offscreen', '.priceToPay .a-offscreen',
                     '#desktop_buybox .a-price .a-offscreen', '#price_inside_buybox', '#kindle-price', '#price']) {
    const e = $(sel); const t = e && e.textContent.trim();
    if (t && /\$\s?\d/.test(t)) { priceTxt = t; break; }
  }
  if (!priceTxt) { const v = ($('#twister-plus-price-data-price') || {}).value; if (v) priceTxt = '$' + v; }
  const listTxt = (() => { const e = $('#corePriceDisplay_desktop_feature_div .basisPrice .a-offscreen') || $('#apex_desktop .basisPrice .a-offscreen') || $('#corePriceDisplay_desktop_feature_div .a-price[data-a-strike="true"] .a-offscreen') || $('#apex_desktop .a-price[data-a-strike="true"] .a-offscreen'); return e ? e.textContent.trim() : null; })();
  const coreText = (['#corePriceDisplay_desktop_feature_div', '#corePrice_feature_div', '#apex_desktop'].map(s => T(s)).find(Boolean)) || '';
  const um = coreText.match(/\(\s*\$\s?([\d,.]+)\s*(?:\$[\d,.]+\s*)?\/\s*([^)]+?)\s*\)/);
  const unit_price = um ? `$${um[1]}/${um[2].trim()}` : (T('.pricePerUnit') || null);
  const savings = (coreText.match(/-\s?(\d+)%/) || [])[1];

  // ---- seller / shipper (two layouts: "Shipper / Seller X" single line, or Ships from / Sold by tabular)
  const bb = $('#desktop_buybox') || $('#buybox') || document.body;
  const bbText = bb.innerText.replace(/Deliver to[^\n]*/g, '').replace(/[ \t]+/g, ' ');
  const seller_line = T('#merchantInfoFeature_feature_div') || null;
  // Tabular layout: label/text pairs (.offer-display-feature-label / -text) -> {"Ships from": "Amazon", "Sold by": "X"}
  const feat = {};
  [...bb.querySelectorAll('.offer-display-feature-label')].forEach(l => {
    const name = l.getAttribute('offer-display-feature-name');
    const t = bb.querySelector('.offer-display-feature-text[offer-display-feature-name="' + name + '"]');
    const k = l.innerText.trim(); if (k && t && !(k in feat)) feat[k] = t.innerText.replace(/\s+/g, ' ').trim().slice(0, 80);
  });
  const strip = s => s ? s.replace(/^(Ships from|Sold by|Shipper \/ Seller)\s*/i, '').trim() : null;
  const ships_from = feat['Ships from'] || feat['Shipper / Seller'] || strip(T('#fulfillerInfoFeature_feature_div')) || null;
  const sold_by = feat['Sold by'] || feat['Shipper / Seller'] || strip(seller_line) || null;
  const sellerAll = [seller_line, ships_from, sold_by].filter(Boolean).join(' | ');
  const amazon_sold = /Amazon\.ca/i.test(sold_by || seller_line || '');
  const amazon_ships = /Amazon/i.test(ships_from || seller_line || '');
  // seller_class: amazon (sold by Amazon.ca) | fba_3p (3P seller, ships from Amazon: fast, Amazon returns)
  //               | mfn_3p (3P ships it themselves: usually slow, often US resellers at 2-5x price)
  const seller_class = !sold_by ? null : amazon_sold ? 'amazon' : /^Amazon/i.test(ships_from || '') ? 'fba_3p' : 'mfn_3p';
  const import_fees = /Import Fees Deposit|import fees/i.test(bbText + ' ' + (T('#amazonGlobal_feature_div') || ''));
  const impAmt = (bbText.match(/\$\s?[\d,.]+\s*(?:Shipping &\s*)?Import Fees Deposit/i) || [])[0] || null;

  // ---- availability & delivery
  const availability = T('#availability') || T('#outOfStock') || null;
  const only_left = ((availability || '').match(/Only (\d+) left/i) || [])[1] || null;
  const dEl = $('#mir-layout-DELIVERY_BLOCK-slot-PRIMARY_DELIVERY_MESSAGE_LARGE [data-csa-c-delivery-time]') || $('[data-csa-c-delivery-time]');
  const delivery = dEl ? (dEl.getAttribute('data-csa-c-delivery-price') + ' delivery ' + dEl.getAttribute('data-csa-c-delivery-time')).replace(/^null /, '') : (T('#mir-layout-DELIVERY_BLOCK-slot-PRIMARY_DELIVERY_MESSAGE_LARGE') || T('#mir-layout-DELIVERY_BLOCK'));
  const fEl = $('#mir-layout-DELIVERY_BLOCK-slot-SECONDARY_DELIVERY_MESSAGE_LARGE [data-csa-c-delivery-time]');
  const fastest = fEl ? 'Fastest ' + fEl.getAttribute('data-csa-c-delivery-time') : null;

  // ---- coupon / promos
  const couponEl = $('#couponBadgeRegularVpc') || $('[id^="couponText"]') || $('.couponLabelText') || $('#vpcButton') || $('#promoPriceBlockMessage_feature_div');
  const coupon = couponEl ? couponEl.innerText.replace(/\s+/g, ' ').replace(/\| Terms|Shop items|Redeem/g, '').trim().slice(0, 160) || null : null;

  // ---- Subscribe & Save (read only)
  const snsRow = $('#snsAccordionRowMiddle') || $('#sns-base-price') || $('#snsDetailPagePrice') || $('[id^="sns-tiered-price"]');
  const sns_price = snsRow ? (offs(snsRow)[0] || (snsRow.innerText.match(/\$\s?[\d,.]+/) || [])[0] || null) : null;
  const sns_note = snsRow ? (snsRow.innerText.match(/Save (?:up to )?\d+%[^\n]{0,60}/i) || [])[0] || null : null;

  // ---- ratings, image
  const rating = (($('#acrPopover') || {}).title || '').trim() || null;
  const reviews = T('#acrCustomerReviewText');
  const li = $('#landingImage') || $('#imgBlkFront') || $('#main-image') || $('#ebooksImgBlkFront');
  let image = li ? (li.dataset.oldHires || li.src) : (($('meta[property="og:image"]') || {}).content || null);
  if (li && !li.dataset.oldHires && li.dataset.aDynamicImage) { try { const k = Object.keys(JSON.parse(li.dataset.aDynamicImage)); image = k[k.length - 1] || image; } catch (e) {} }

  // ---- variants: parse dimensionValuesDisplayData / dimensions out of inline scripts
  let variants = null;
  const scr = [...document.scripts].map(s => s.textContent).find(t => t.includes('dimensionValuesDisplayData'));
  if (scr) {
    const grab = key => { const i = scr.indexOf('"' + key + '"'); if (i < 0) return null;
      let j = scr.indexOf(':', i) + 1; while (/\s/.test(scr[j])) j++;
      const open = scr[j], close = open === '{' ? '}' : open === '[' ? ']' : null; if (!close) return null;
      let d = 0, k = j; for (; k < scr.length; k++) { if (scr[k] === open) d++; else if (scr[k] === close && --d === 0) break; }
      try { return JSON.parse(scr.slice(j, k + 1)); } catch (e) { return null; } };
    const by = grab('dimensionValuesDisplayData') || {};
    const pm = scr.match(/"parentAsin"\s*:\s*"([A-Z0-9]{10})"/);
    variants = { dims: grab('dimensions') || null, labels: grab('variationDisplayLabels') || null, parent_asin: pm ? pm[1] : null,
                 n: Object.keys(by).length, by_asin: by };
  }
  const twister = [...document.querySelectorAll('#twister .a-row .selection, #variation_size_name .selection, #variation_color_name .selection, [id^="inline-twister-expanded-dimension-text"]')].map(e => e.innerText.trim()).filter(Boolean);

  // ---- no featured offer ("See All Buying Options"): read the all-offers panel via same-origin GET (read only)
  let no_featured_offer = false, offers = null;
  if (!priceTxt && $('#buybox-see-all-buying-choices, #unqualifiedBuyBox')) {
    no_featured_offer = true;
    try {
      const h = await (await fetch('/gp/product/ajax/aodAjaxMain/?asin=' + asin + '&pc=dp&experienceId=aodAjaxMain', { credentials: 'include' })).text();
      const d = new DOMParser().parseFromString(h, 'text/html');
      offers = [...d.querySelectorAll('#aod-pinned-offer, #aod-offer')].map(o => {
        const p = o.querySelector('.apexPriceToPay .aok-offscreen, .aok-offscreen, .a-price .a-offscreen');
        const c = (...ss) => { for (const s of ss) { const x = o.querySelector(s); if (x && x.innerText.trim()) return x.innerText.replace(/\s+/g, ' ').trim().slice(0, 60); } return null; };
        const dt = o.querySelector('[data-csa-c-delivery-time]');
        return { price: p ? p.textContent.trim() || null : null, condition: c('#aod-offer-heading'), ships_from: c('#aod-offer-shipsFrom .a-col-right'),
                 sold_by: c('#aod-offer-soldBy .a-col-right a', '#aod-offer-soldBy .a-col-right'), delivery: dt ? dt.getAttribute('data-csa-c-delivery-time') : null };
      }).filter(o => o.price);
    } catch (e) { offers = [{ error: String(e).slice(0, 100) }]; }
  }

  const requested = (location.pathname.match(/\/dp\/([A-Z0-9]{10})/) || [])[1] || null;
  return {
    ready: true, asin, requested_asin: requested, asin_mismatch: !!(requested && asin && requested !== asin), url: location.origin + '/dp/' + asin, title,
    price: priceTxt, price_num: money(priceTxt), list_price: listTxt, savings_pct: savings ? +savings : null, unit_price,
    seller_line, ships_from, sold_by, seller_class, amazon_sold, amazon_ships, third_party: !!sellerAll && !amazon_sold, import_fees, import_fee_text: impAmt,
    availability, only_left: only_left ? +only_left : null, delivery, fastest, coupon,
    no_featured_offer, offers, sns_price, sns_note, rating, reviews, image, selected: twister, variants
  };
})()

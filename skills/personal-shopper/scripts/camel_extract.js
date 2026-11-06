// camelcamelcamel.ca (Canada locale) price-history extractor: iMac CDP extractor (verified 2026-10-08).
// The VPS is Cloudflare-walled; run this through the iMac's real Chrome:
//   scp -q camel_extract.js sumeet@100.119.136.41:.hermes/
//   ssh -o BatchMode=yes sumeet@100.119.136.41 \
//     'cd ~/.hermes && costco-venv/bin/python mac_cdp_fetch.py camel_extract.js https://ca.camelcamelcamel.com/product/<ASIN>'
// URL shape: https://ca.camelcamelcamel.com/product/<ASIN>  (the "ca." subdomain = amazon.ca prices, CAD).
// Returns {ready, asin, title, tracked_since, current:{price,as_of}, rows:{amazon|third_new|third_used:
//   {lowest,lowest_date,highest,highest_date,current,current_date,average}}, list_price, last_scan, chart, verdict}
// verdict compares the Amazon current vs its average/lowest (a quick "is this a good price" signal).
(() => {
  const t = document.body ? document.body.innerText : '';
  if (/Just a moment|Verify you are human|Attention Required/i.test(document.title + t.slice(0, 400)))
    return { ready: false, cf: true };
  if (/couldn't find that product|Product not found|404/i.test(document.title + t.slice(0, 600)) && !/Lowest Ever/i.test(t))
    return { ready: true, not_tracked: true, title: document.title };
  if (!/Lowest Ever/i.test(t)) return { ready: false, head: t.slice(0, 150) };

  const num = s => { const m = (s || '').match(/\$\s?([\d,]+\.\d{2})/); return m ? parseFloat(m[1].replace(/,/g, '')) : null; };
  const dt = s => { const m = (s || '').match(/\(([A-Z][a-z]{2} \d{1,2}, \d{4})\)/); return m ? m[1] : null; };
  const tb = [...document.querySelectorAll('table')].find(x => /Lowest Ever/.test(x.innerText));
  const rows = {};
  if (tb) {
    const hdr = [...tb.rows[0].cells].map(c => c.innerText.trim().toLowerCase());
    const col = name => hdr.findIndex(h => h.startsWith(name));
    for (const r of [...tb.rows].slice(1)) {
      const c = [...r.cells].map(x => x.innerText.trim().replace(/\s+/g, ' '));
      const label = c[0];
      const key = /^Amazon/.test(label) ? 'amazon' : /New/.test(label) ? 'third_new' : /Used/.test(label) ? 'third_used' : label;
      const g = i => (i >= 0 ? c[i] : null);
      const lo = g(col('lowest')), hi = g(col('highest')), cu = g(col('current')), av = g(col('average'));
      rows[key] = { lowest: num(lo), lowest_date: dt(lo), highest: num(hi), highest_date: dt(hi),
                    current: num(cu), current_date: dt(cu), average: num(av) };
    }
  }
  const fields = {};
  const pf = document.querySelector('table.product_fields');
  if (pf) for (const r of pf.rows) if (r.cells.length >= 2) fields[r.cells[0].innerText.trim()] = r.cells[1].innerText.trim();
  const since = (t.match(/since we began monitoring it on (?:on )?([A-Z][a-z]{2} \d{1,2}, \d{4})/) || [])[1] || null;
  const asOf = (t.match(/\$([\d,.]+)\s*\n\s*Amazon Price\s*\n\s*as of ([^\n]+)/) || []);
  const chartImg = [...document.images].map(i => i.src).find(s => /charts\.camelcamelcamel\.com/.test(s)) || null;
  // Use the Amazon (sold+shipped by Amazon) row if it has data, else 3rd Party New.
  const basis = (rows.amazon && rows.amazon.average != null) ? 'amazon' : (rows.third_new && rows.third_new.average != null) ? 'third_new' : null;
  const a = basis ? rows[basis] : {};
  let verdict = null;
  if (a.current != null && a.average != null) {
    const vsAvg = Math.round((a.current / a.average - 1) * 100);
    verdict = (a.lowest != null && a.current <= a.lowest * 1.03 ? 'at/near all-time low; ' : '') + (vsAvg <= 0 ? `${-vsAvg}% below` : `${vsAvg}% above`) + ` ${basis} average (camel 'current' is as of ${a.current_date})`;
  }
  const title = (document.querySelector('h2') || {}).innerText || document.title.split(' | ')[0];
  return {
    ready: true, asin: fields.SKU || (location.pathname.match(/product\/([A-Z0-9]{10})/) || [])[1] || null,
    title: title.split(' | ')[0].trim(), tracked_since: since,
    current: asOf.length ? { price: num('$' + asOf[1]), as_of: asOf[2].trim() } : null,
    rows, list_price: num(fields['List price']), last_scan: fields['Last update scan'] || null,
    last_tracked: fields['Last tracked'] || null, chart: chartImg, verdict
  };
})()

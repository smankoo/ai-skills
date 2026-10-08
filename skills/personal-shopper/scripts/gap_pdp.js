(async () => {
  // Gap / Old Navy / BR Canada PDP (or category) extractor for mac_cdp_fetch.py. Returns {ready:true,...}
  const t = document.body ? document.body.innerText : '';
  if (/Access Denied/i.test(document.title)) return {ready: true, blocked: true, title: document.title};
  const pids = [...new Set([...document.querySelectorAll('a[href*="pid="]')].map(a => (a.href.match(/pid=(\d+)/) || [])[1]).filter(Boolean))];
  if (!/product\.do/.test(location.href)) {
    if (pids.length < 3) return {ready: false, title: document.title};
    return {ready: true, kind: 'category', title: document.title, pids: pids.slice(0, 40)};
  }
  const labels = [...document.querySelectorAll('label[for^="pdp_buybox_dimension_"]')];
  if (!labels.length) return {ready: false, title: document.title};
  const sizes = labels.map(l => ({size: (l.getAttribute('for') || '').replace('pdp_buybox_dimension_', ''),
                                  oos: /--unavailable/.test(l.className)}));
  const h1 = (document.querySelector('h1') || {}).innerText || '';
  const prices = [...new Set((t.match(/(?:CA)?\$\d{1,4}\.\d\d/g) || []))].slice(0, 4);
  const html = document.documentElement.innerHTML;
  const comp = [...new Set((t + ' ' + html).match(/\d{1,3}% (?:[A-Za-z]+ )?(?:cotton|polyester|wool|linen|elastane|spandex|nylon|viscose|rayon|lyocell|modal|acrylic|cashmere|silk|recycled [a-z]+|polyamide|tencel)[^<\n"]{0,60}/gi) || [])].slice(0, 6);
  const og = (document.querySelector('meta[property="og:image"]') || {}).content || '';
  const colour = ((t.match(/Color:\s*([^\n]+)/i) || t.match(/Colour:\s*([^\n]+)/i) || [])[1] || '').trim();
  return {ready: true, kind: 'pdp', url: location.href, title: document.title, h1, prices, colour, sizes, comp, image: og};
})()

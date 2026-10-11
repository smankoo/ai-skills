// nsf_sport.js — NSF Certified for Sport search results (iMac via mac_cdp_fetch.py). 2026-10-11 probe.
// URL: https://www.nsfsport.com/certified-products/search-results.php?keyword=<brand or product>
(() => {
  if (/just a moment/i.test(document.title)) return {ready: false};
  const ul = document.querySelector('#filterul');
  if (!ul) return {ready: false};
  const items = [...ul.querySelectorAll('li')].map(li => {
    const a = li.querySelector('a[href]');
    return {text: li.innerText.replace(/\s+/g, ' ').trim().slice(0, 200), href: a ? a.href : null};
  }).filter(x => x.text);
  const noRes = document.querySelector('.form_noresults');
  return {ready: true, n: items.length, items: items.slice(0, 40),
    results_yes: (document.querySelector('.results_yes') || {}).innerText || null,
    noresults_visible: !!(noRes && noRes.offsetParent), title: document.title};
})()

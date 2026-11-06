#!/usr/bin/env python3
"""
cert_lookup.py — check a supplement brand/product against the sport-certification registries.

  python3 cert_lookup.py "<brand>" ["<product words>"]

Registries (VPS stdlib, no browser needed, verified 2026-10-11):
  INFORMED CHOICE  https://choice.wetestyoutrust.com/certified-products
      One ~275 KB Drupal page with EVERY certified product, grouped by brand:
      div.grid-item-wrapper > <h4>Brand</h4> > .views-field-title .field-content = product name.
      Region tags are in the product name ("(USA)", "(CAN)", "(Europe)"). No pagination.
  NSF CERTIFIED FOR SPORT  https://www.nsfsport.com/certified-products/search-results.php?keyword=<q>
      Server-rendered; each SKU is <a href="/certified-products/listing-detail.php?id=N"> followed by
      p.results__product-name + p.results__company-name (family rows nest SKU rows; parse pairs, not <li>).
      Search by BRAND ONLY: multi-word keywords ("biosteel whey isolate") return an empty list; the script
      filters product words locally. Verified 2026-10-11 (evening, DB back up): BioSteel Whey Protein
      Isolate Vanilla (Canada) = NSF match; Thorne = 67 listings; PVL Whey Gold = Informed Choice only.
      ⚠️ Earlier on 2026-10-11 (02:00) the backend was DOWN — every query
      (even 'thorne', 'whey') returned an empty list, and the page body carried
      "ORA-12541: TNS:no listener" (Oracle DB offline). Same from VPS curl, VPS browser, iMac and
      web_extract. The script detects that and reports status "registry_down" instead of
      "not certified". An empty NSF list is only a negative if no ORA- error is present.
      Fallback while down: the brand's own PDP badge + web_search snippets of the NSF results page
      (label as "unverified").

Output: one JSON object {query, informed_choice:{status, matches[]}, nsf_sport:{status, matches[]}}.
status = "match" | "no_match" | "registry_down" | "error:<msg>".
Verified 2026-10-11: "Dymatize" -> Informed Choice match (7 products incl. "Elite 100% Whey Protein").
"""
import html
import json
import re
import sys
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/141.0.0.0 Safari/537.36")


def get(url):
    req = urllib.request.Request(url, headers={"user-agent": UA, "accept-language": "en"})
    with urllib.request.urlopen(req, timeout=45) as r:
        return r.read().decode("utf-8", "replace")


def clean(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def norm(s):
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def words_in(words, text):
    t = (text or "").lower()
    return all(w in t for w in words)


def informed_choice(brand, words):
    try:
        h = get("https://choice.wetestyoutrust.com/certified-products")
    except Exception as e:  # noqa: BLE001
        return {"status": f"error:{e}", "matches": []}
    out = []
    for blk in h.split('class="grid-item-wrapper"')[1:]:
        b = re.search(r"<h4[^>]*>(.*?)</h4>", blk, re.S)
        if not b:
            continue
        bname = clean(b.group(1))
        if norm(brand) not in norm(bname) and norm(bname) not in norm(brand):
            continue
        prods = [clean(p) for p in re.findall(r'class="field-content">(.*?)</span>', blk, re.S)]
        for p in prods:
            if words_in(words, p):
                out.append({"brand": bname, "product": p})
    if not out and "grid-item-wrapper" not in h:
        return {"status": "error:layout changed (no grid-item-wrapper)", "matches": []}
    return {"status": "match" if out else "no_match", "matches": out}


def nsf_sport(brand, words):
    q = brand  # NSF keyword search goes empty on long multi-word queries; search by brand, filter words locally
    try:
        h = get("https://www.nsfsport.com/certified-products/search-results.php?keyword="
                + urllib.parse.quote(q))
    except Exception as e:  # noqa: BLE001
        return {"status": f"error:{e}", "matches": []}
    if re.search(r"ORA-\d{5}", h):
        return {"status": "registry_down", "detail": re.search(r"ORA-\d{5}[^<]*", h).group(0).strip(),
                "matches": []}
    # Results are nested: a family <li> (href="#") wraps a <ul> of per-SKU <li>s that link to
    # listing-detail.php?id=N. A regex on <li>…</li> stops at the first nested </li> (bug fixed
    # 2026-10-11: Thorne returned 2 of 77). Instead, pair every SKU link with its name/company.
    items, seen = [], set()
    for m in re.finditer(r'href="(/certified-products/listing-detail\.php\?id=(\d+))".*?'
                         r'results__product-name">(.*?)</p>\s*<p class="results__company-name">(.*?)</p>',
                         h, re.S):
        if m.group(2) in seen:
            continue
        seen.add(m.group(2))
        items.append({"product": clean(m.group(3)), "company": clean(m.group(4)),
                      "href": "https://www.nsfsport.com" + m.group(1)})
    hits = [i for i in items if norm(brand) in norm(i["company"] + " " + i["product"])
            and all(norm(w) in norm(i["product"]) for w in words)]
    return {"status": "match" if hits else "no_match", "matches": hits[:30], "n_listed": len(items)}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    brand = sys.argv[1]
    words = [w.lower() for w in " ".join(sys.argv[2:]).split()]
    print(json.dumps({"query": {"brand": brand, "words": words},
                      "informed_choice": informed_choice(brand, words),
                      "nsf_sport": nsf_sport(brand, words)}, ensure_ascii=False, indent=1))

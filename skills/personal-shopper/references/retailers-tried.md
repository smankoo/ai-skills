# Retailers tried — reconnaissance ledger

**Purpose.** A running log so the twice-daily reconnaissance job never re-investigates a retailer
it already cracked. Each run picks a retailer **not already `done` below**, works out the best way
to pull product data (API / frontend / Shopify JSON / rendered PDP), records the mechanics in
`retailer-recipes.md`, and adds a row here.

**Status legend**
- `done` — a working, tested extraction recipe exists in `retailer-recipes.md`.
- `blocked` — a hard wall with no VPS-side workaround found yet (see `retail-bot-wall-bypass` skill).
- `partial` — some data extractable, but incomplete (e.g. price but not composition/stock).
- `wip` — investigated but not yet a repeatable recipe.

**How to use each run**
1. Read this whole file first. Do NOT pick a retailer with status `done`.
2. Prefer a retailer that fits Sumeet's household (Canadian delivery; natural-fibre-friendly lines;
   kids + adults; his stated stores) — but variety across runs is the goal.
3. After investigating, append/update a row here AND push. One retailer per run is plenty.

| Retailer | Country | Method that works | Status | Recipe? | Last verified |
|---|---|---|---|---|---|
| Uniqlo CA | CA | Public JSON API (`x-fr-clientid: uq.ca.web-spa`), same-origin fetch | done | yes | 2026-08-13 |
| Herschel | Global | Shopify storefront JSON (`/products/<handle>.json`, `suggest.json`) | done | yes | 2026-08-13 |
| Simons | CA | JSON-LD via same-origin fetch (Mac; VPS Cloudflare-blocked) | done | yes | 2026-08-08 |
| Gap CA | CA | `/browse/product.do` HTML, per-size `--unavailable` label | done | yes | 2026-08-04 |
| Old Navy CA | CA | Same Gap platform; constructor.io search; `pdp-dimension-instock` | done | yes | 2026-08-08 |
| Joe Fresh | CA | PDP SSR embeds `sizes[]` with `disabled:false` | done | yes | 2026-08-08 |
| H&M CA | CA | Cloudflare (same class as Simons) — Mac delegation only | blocked | note | 2026-08-08 |
| Aritzia | CA | Cloudflare (same class as Simons) — Mac delegation only | blocked | note | 2026-08-08 |
| Costco.ca | CA | Press-and-Hold interactive challenge; deep product URLs sometimes clear | blocked | note | 2026-08-12 |
| Wayfair.ca | CA | Press-and-Hold; CDP windowed Chrome on Mac works for product pages | partial | note | 2026-08-12 |
| Pottery Barn Kids CA | CA | Loads clean via CDP windowed Chrome on Mac | done | note | 2026-08-12 |
| The Brick | CA | Press-and-Hold on grids; CDP windowed Chrome + deep links works | partial | note | 2026-08-12 |
| The Children's Place | CA | Rendered-DOM via web_extract + `childrensplace_extract.py` (no JSON-LD/API) | done | yes | 2026-08-15 |
| Carter's / OshKosh CA | CA | JSON-LD `ProductGroup` (per-size price+stock) via CDP Chrome on Mac; `carters_extract.py`. VPS fully walled (CF+PerimeterX) | done | yes | 2026-08-15 |
| Reitmans | CA | Shopify `/products/<handle>.js` (price/stock, cents) + PDP-HTML `<li class="p3">` composition; `reitmans_extract.py`. No bot wall, VPS-side | done | yes | 2026-08-16 |
| Tommy Hilfiger CA | CA | JSON-LD `Product` (name/price/avail/image) + `div.content-column` composition + `label.size-enabled/-disabled` per-size stock, via CDP Chrome on Mac; `tommy_extract.py`. VPS Akamai-walled (hard 403) | done | yes | 2026-08-17 |
| Roots CA | CA | JSON-LD `Product` + static PDP-HTML (`Fibre Content`/`ABOUT` composition, `size-value` swatches); pure `urllib`, NO bot wall; `roots_extract.py` | done | yes | 2026-08-17 |
| Zara CA | CA | JSON-LD `ProductGroup` (per-size×colour price+stock+composition, all in one block) via CDP Chrome on Mac; `zara_extract.py`. VPS fully Akamai-walled (curl/web_extract/JSON-API all hard-403) | done | yes | 2026-08-18 |
| La Vie En Rose | CA | JSON-LD `ProductGroup` (per-size price/stock/strike) + PDP `<li><p>NN% Fibre</p>` composition; `lavieenrose_extract.py`. EPiServer, NO bot wall, VPS-side `urllib` | done | yes | 2026-08-19 |
| Sport Chek | CA | JSON-LD `Product` (name/brand/image/desc) + `.nl-price` / `.nl-variants__variant` DOM, via CDP Chrome on Mac; `sportchek_extract.py`. Canadian Tire/FGL "Nucleus" stack; VPS Akamai-walled (curl/web_extract/APIM all 403); data API is 410 Gone | done | yes | 2026-08-19 |
| Walmart CA | CA | JSON-LD `Product`/`ProductGroup` (per-size price+stock) + `__NEXT_DATA__` `specifications`; composition from `longDescription`. Via CDP Chrome on Mac WITH homepage warm-up + same-tab nav (cold hit → `/blocked`); `walmart_extract.py`. VPS PerimeterX-walled | done | yes | 2026-08-19 |
| Frank And Oak | CA | Shopify `/products/<handle>.js` (price/stock/image + composition in `description` `Content:` line); `frankandoak_extract.py`. NO bot wall, pure `urllib` VPS-side | done | yes | 2026-08-20 |
| Indigo / Chapters | CA | Shopify `/products/<handle>.js` (per-format price+stock, cents) + PDP JSON-LD `ProductGroup` (ISBN/publisher/rating) + `<title>` author; `indigo_extract.py`. Books & gifts (gift track); NO bot wall, pure `urllib` VPS-side. Old `chapters.indigo.ca` retired → `indigo.ca` | done | yes | 2026-08-20 |
| ALDO | CA | Rendered-PDP JSON-LD `ProductGroup` (per-size price+stock+image) + static Materials accordion (`Material:`/`Lining:`/`Sole:`) composition; `aldo_extract.py`. Adult footwear/accessories; NO bot wall, pure `urllib` VPS-side. Footwear `.js`/`.json` 404 (use PDP); `en-ca/` prefix required | done | yes | 2026-08-21 |
| The Ordinary / Deciem | CA | PDP JSON-LD `Product` (name/price CAD/avail/image) + static `data-original-ingredients` attribute (full INCI); `theordinary_extract.py`. Skincare (gift/personal-care); Demandware, NOT Shopify; NO bot wall, pure `urllib` VPS-side | done | yes | 2026-08-21 |
| Crocs CA | CA | PDP JSON-LD `Product` (name/price/image/rating) + `app.product.data.cache[...].masterData` JS block (per-size `inStock`+`ATS`, sale, OOS colours); `crocs_extract.py`. Adult+kids footwear; SFCC/Demandware, NO bot wall, pure `urllib` VPS-side. Croslite foam → no fibre-% (natural-fibre gate N/A) | done | yes | 2026-08-22 |
| The Body Shop CA | CA | Shopify `/products/<handle>.js` (price/stock CENTS, per-variant `available`) + PDP-HTML first `<span class="metafield-multi_line_text_field">` (INCI) + `% natural origin` from desc; `thebodyshop_extract.py`. Beauty/personal-care (gift track); NO bot wall, pure `urllib` VPS-side. Cosmetic → fibre gate N/A | done | yes | 2026-08-23 |
| Kotn | CA | Next.js `__NEXT_DATA__` (price/composition/image) + headless-Shopify Storefront GraphQL by GID (per-size live stock); `kotn_extract.py`. Egyptian/organic-cotton essentials — top natural-fibre source; NO bot wall, pure `urllib` VPS-side. NOT a Shopify front end (`.js`/`.json` on kotn.com return SPA shell) | done | yes | 2026-08-23 |
| IKEA CA | CA | Rendered-DOM via `web_extract` + `ikea_extract.py` (name/price/article/composition/image). NO JSON-LD; curl/`.json`/iows/ingka API all Cloudflare-403. Home/furniture/textiles; live STOCK not in render (null). | done | yes | 2026-08-24 |
| Toys R Us CA | CA | **No online catalog** — site is store-locator/FAQ only ("shop in-store"); no product/PDP pages exist to scrape. | n/a | note | 2026-08-24 |
| Tilley | CA | Shopify `/products/<handle>.js` (price/stock/variants, cents) + PDP `<h6>Fabric</h6>` composition; `tilley_extract.py`. NO bot wall, pure `urllib` VPS-side. JSON-LD prices are USD | done | yes | 2026-08-24 |
| Staples CA | CA | Shopify `/products/<handle>.js` (price/stock cents + rich `tags[]`: brand/model/UPC/rating/breadcrumb/material); `staples_extract.py`. `.json`/PDP/`suggest.json` Cloudflare-403, `.js` open; pure `urllib` VPS-side | done | yes | 2026-08-24 |
| MEC | CA | Rendered-DOM via `web_extract` + `mec_extract.py` (title/price/sale/composition/colours/sizes/style-id/made-in/image). Headless Next.js over BigCommerce (`s-xw5rh7060c`); curl→Cloudflare-403, NO JSON-LD, NO API. Renders clean first pass. Live per-size STOCK not in render (XHR). Natural-fibre: organic-cotton tees + merino knits | done | yes | 2026-08-25 |
| ASICS CA | CA | Rendered-DOM via `web_extract` + `asics_extract.py` (name/price/sale/avail/style#/rating/image). Adobe Commerce/Magento; curl/`.json`/API all hard-403, NO JSON-LD, NO Shopify. Renders clean FIRST pass. Footwear → natural-fibre gate N/A; live per-size stock not in render (XHR) | done | yes | 2026-08-25 |
| Mountain Warehouse CA | CA | **Static HTML from a plain `urllib` GET** (Next.js over BigCommerce `s-nb5it5hcrj`) — price/was/%off (aria-label), `Main fabric:` composition, per-size stock (`disabled=""` on `VariantOption` input), og:image; `mountainwarehouse_extract.py`. NO bot wall, VPS-side. Value outdoor apparel; strong organic-cotton/merino natural-fibre lines | done | yes | 2026-08-26 |

| Mark's | CA | CDP Chrome on Mac + **Network-intercept** the app's own XHR: `productFamily/<id>` (name/brand/image/`specifications[]` composition/`optionIds[]` size-colour) + `PriceAvailability?pCode=<id>` (price/sale/`Corporate.Quantity` live stock); `marks_extract.py`. Canadian Tire/FGL stack; VPS Akamai-403; do NOT replay XHR (401/400) — intercept only. Denver Hayes/WindRiver = cotton-rich | done | yes | 2026-08-26 |
| Hudson's Bay / thebay.com | CA | DEFUNCT — Hudson's Bay closed 2025; `thebay.com` 301-redirects to canadiantire.ca (Stripes home-goods collab only). No apparel catalog to scrape. | n/a | note | 2026-08-26 |
| Sephora CA | CA | Rendered buy-box via `web_extract` + `sephora_extract.py` (name/list/sale price + %off). Product API (`/api/v3/catalog/products/<PID>`) Akamai-403 from VPS; NO JSON-LD/`__NEXT_DATA__`. Beauty/personal-care (gift track); fibre gate N/A. Image/INCI/stock hydrate via walled XHR (needs Mac CDP) → **partial** | partial | yes | 2026-08-27 |
| Winners CA | CA | **No online catalog** — winners.ca is store-locator/articles only ("Products shown are representative… styles vary by store"; shop in-store). Like Toys R Us. Nothing to scrape. | n/a | note | 2026-08-27 |
| Canadian Tire | CA | `web_extract` renders only the shell (products hydrate from Akamai-walled APIM `apim.canadiantire.ca` / `/api/v1/product/...`, hard-403 from VPS — same FGL/Nucleus stack as Sport Chek/Mark's). Render leaks the `subscription-key` but the endpoint still 403s VPS-side → Mac CDP Network-intercept needed (see Mark's recipe). | wip | note | 2026-08-27 |
| RONA / Etsy / EyeBuyDirect.ca / Party City / Bath & Body Works CA / Michael Kors CA / Michaels CA | CA | Hard-walled from VPS: RONA & Etsy & EyeBuyDirect = DataDome/Akamai on PDP (`web_extract` → DataDome captcha / Akamai shell); Party City & B&BW = Akamai/PerimeterX; Michael Kors & Michaels = curl-403, no render path found. All would need Mac CDP. | blocked | note | 2026-08-27 |
| Brilliant Earth | CA | Rendered-DOM via `web_extract` + `brilliantearth_extract.py` (title/CAD price/stock/metal/style/gemstone/chain/image). GIFT track fine jewelry — natural-fibre gate N/A. curl→Cloudflare-403 "Verifying"; NO JSON-LD/API. Renders clean FIRST pass. **Use `/en-ca/` for CAD**; distinguish finished piece (`ADD TO BAG`) from design-your-own setting (`Setting Only`) | done | yes | 2026-08-28 |
| Decathlon CA | CA | CDP Chrome on Mac: nav→13s→click Specifications accordion→read spec table + fibre regex; `decathlon_extract.py`. VPS hard Cloudflare-403 on curl+all APIs; `web_extract` renders price/name/rating only (composition behind collapsed accordion, no image/stock). Value sports/outdoor (Domyos/Quechua); "Cotton" names lie about blend — read the % | done | yes | 2026-08-29 |
| Everlane | US (ships CA) | Shopify `/products/<handle>.js` (price/stock/variants, CENTS **USD**) + PDP-HTML static `Materials:<ul><li>…</li></ul>` accordion (composition); `everlane_extract.py`. NO bot wall, pure `urllib` VPS-side. Top natural-fibre source (100% organic-cotton/cashmere/merino/linen). ⚠️ prices are USD not CAD; one handle per colourway | done | yes | 2026-08-29 |
| Aritzia | CA | RE-TESTED 2026-08-29: still hard-walled — curl 403 AND `web_extract` browser backend 403 ("anti-bot protection: HTTP 403"). No new VPS angle; Mac-CDP only, as before | blocked | note | 2026-08-29 |
| Quince | CA (`/ca/`) | Static HTML from plain `urllib` GET: JSON-LD `@graph`→`ProductGroup.hasVariant[]` (per-colour×size price CAD + stock + image) + `__NEXT_DATA__` `product.details` exact fibre %; `quince_extract.py`. NO bot wall, VPS-side. Top natural-fibre source (100% organic-cotton/cashmere/linen/silk); NAMES lie about blends — read the % | done | yes | 2026-08-30 |
| Province of Canada | CA | Shopify `/products/<handle>.js` (price cents + per-size `available`) + `.json` `body_html` prose composition; `provinceofcanada_extract.py`. NO bot wall, pure `urllib` VPS-side. Made-in-Canada organic/GOTS-cotton basics — strong natural-fibre source. `.js` currency is null → hard-code CAD | done | yes | 2026-08-30 |
| tentree | CA | Shopify `/products/<handle>.js` (price cents + per-size `available`, sku, image) + PDP-HTML `fabric-composition="…"` attribute (authoritative composition); `tentree_extract.py`. NO bot wall, pure `urllib` VPS-side. Sustainable organic-cotton/hemp/TENCEL — but TreeBlend tri-blends are ~45% recycled poly → read the %; TENCEL=natural, recycled poly=synthetic | done | yes | 2026-08-30 |
| Oak + Fort | CA | Shopify `/products/<handle>.js` (price cents + per-variant `available`, image) + static PDP "Materials & Care" accordion (after `id=filter-materials-care-heading`) composition; `oakandfort_extract.py`. NO bot wall, pure `urllib` VPS-side. Minimalist DTC (women/men); real 100% linen/cotton but "Blend" = ~45% rayon → read the % | done | yes | 2026-08-31 |
| Peace Collective | CA | Shopify `/products/<handle>.js` (price cents + per-size `available`, image) + PDP-HTML `multi_line_text_field` fibre bullet (`• NN% Cotton…`) composition; `peacecollective_extract.py`. NO bot wall, pure `urllib` VPS-side. Toronto DTC tees/crewnecks — 100% cotton essentials line, but fleece/licensed = 60/40 cotton-poly → read the %. Must use `www.` host | done | yes | 2026-08-31 |
| Naked & Famous Denim | CA | Shopify `/products/<handle>.js` alone — price cents + per-size `available` + image + composition (embedded in `.js` `description` field as `<li>NN% Cotton…</li>`); `nakedandfamous_extract.py`. NO bot wall, pure `urllib` VPS-side. Montreal selvedge denim — top men's natural-fibre source (raw = 100% cotton, stretch = 98/2 cotton/elastane). `.js` has NO currency → hard-code CAD; JSON-LD price is USD (wrong for CA) | done | yes | 2026-09-01 |
| Icebreaker CA | CA | Shopify `/en-ca/products/<handle>.js` (price cents + per-size `available` + image) + PDP-HTML `<strong>Fabric content</strong><p>…%…</p>` (authoritative composition, NOT in `.js`); `icebreaker_extract.py`. NO bot wall, pure `urllib` VPS-side. Merino specialist — top natural-fibre source (100% merino tees + TENCEL/merino Cool-Lite blends). `/en-ca/` prefix MANDATORY (else 302→USD); JSON-LD price is stale USD | done | yes | 2026-09-01 |
| Patagonia CA | CA | Rendered-DOM via `web_extract` + `patagonia_extract.py` (title/price/sale/composition/style/COO/colours). SFCC/Demandware; VPS hard-walled (curl→decoy 10-byte `Not found` 404, OCAPI 404, no JSON-LD/Shopify). web_extract INTERMITTENT (retry 2-3×). Composition YES; **image + per-size stock NOT in render → Mac CDP** (og:image + swatch click). Top organic-cotton/hemp natural-fibre source; tech/fleece lines = recycled poly (fail gate) | partial | yes | 2026-09-02 |
| Banana Republic CA | CA | `web_extract` renders the PDP on `bananarepublic.gapcanada.ca/browse/product.do?pid=<pid>` (Gap Canada platform) — title/price/sale/rating/images/offered-sizes; `bananarepublic_extract.py`. Composition (Fabric&Care accordion) + per-size stock DON'T render → Gap `__G` loaded-tab fetch / Mac CDP. VPS Akamai-403 on curl/API/robots. `www.bananarepublic.ca` `.jsp` host is marketing-only | partial | yes | 2026-09-03 |
| Unbound Merino | CA (ships) | Shopify `/products/<handle>.js?currency=CAD` (price cents CAD + per-variant `available`, option1=colour/option2=size, image) + PDP-HTML first `<li>` under `ul.product-tab__details-list` composition; `unboundmerino_extract.py`. NO bot wall, pure `urllib` VPS-side. Merino specialist — 100% merino tees/base layers + merino/linen shirts (top natural-fibre source). ⚠️ store DEFAULTS to USD → MUST append `?currency=CAD`; merino socks ~40% nylon fail 70% gate | done | yes | 2026-09-02 |

<!-- APPEND NEW ROWS ABOVE THIS LINE. Keep newest investigations discoverable. -->

## Candidate queue (not yet tried — good picks for future runs)

### ⭐ CONFIRMED FROM SUMEET'S YNAB PURCHASE HISTORY — prioritize these first

These are retailers Sumeet has **actually purchased from** (verified against his YNAB payee list,
2026-08-13). A recon run should prefer these over speculative picks — a working recipe here has
immediate real-world value. Grouped by role; ones already cracked are marked.

**Apparel & footwear**
- Uniqlo Canada — ✅ `done` (see recipe). His confirmed kids' store.
- Old Navy CA — ✅ `done`. His confirmed kids' store.
- Gap CA — ✅ `done`.
- La Maison Simons — ✅ `done` (Mac delegation).
- Aritzia — `blocked` (Cloudflare); **re-tested 2026-08-29 with the new `web_extract` browser backend → still hard 403** (both curl and headless render). Mac-CDP only; don't re-probe from the VPS.
- **Zara CA** (zara.com/ca) — ✅ `done` (see recipe). Bought at Square One. VPS Akamai-walled → Mac CDP; JSON-LD has it all.
- **The Children's Place** (childrensplace.com/ca) — ✅ `done` (see recipe). Kids' workhorse clothes.
- **Carter's / OshKosh CA** (cartersoshkosh.ca) — ✅ `done` (see recipe). Baby/toddler, mostly 100% cotton. VPS-walled → Mac CDP.
- **Reitmans** (reitmans.com) — ✅ `done` (see recipe). Women's (Priyanka); Shopify, no bot wall.
- **La Vie En Rose** (lavieenrose.com) — ✅ `done` (see recipe). Lingerie/sleepwear/loungewear; EPiServer, NO bot wall, VPS-side.
- **Tommy Hilfiger CA** (ca.tommy.com) — ✅ `done` (see recipe). Cotton oxfords/chinos/polos (adult) + mostly-cotton kids' tees/shirts. VPS Akamai-walled → Mac CDP.
- **Michael Kors CA** — accessories/gifts. `blocked` (curl-403, no VPS render path; would need Mac CDP).
- **Aldo** (aldoshoes.com) — ✅ `done` (see recipe). Adult footwear/accessories. Shopify but footwear `.js` 404s → rendered-PDP JSON-LD; NO bot wall, VPS-side. (skill's "never order kids' shoes" rule; adults OK.)
- **Crocs CA** (crocs.ca) — ✅ `done` (see recipe). Adult + kids footwear; SFCC/Demandware, NO bot wall, VPS-side. Croslite foam → no fibre-% (natural-fibre gate N/A). Skill's "never order kids' shoes" rule applies.
- **ASICS Canada** (asics.com/ca) — ✅ `done` (see recipe). Athletic footwear, his fitness angle. Adobe Commerce/Magento; VPS hard-403 on curl/API → `web_extract` renders clean first pass. Footwear → natural-fibre gate N/A.
- **Sport Chek** (sportchek.ca) — ✅ `done` (see recipe). Athletic/outdoor, his fitness angle. Canadian Tire/FGL stack; VPS Akamai-walled → Mac CDP; JSON-LD + `.nl-*` DOM.
- **Winners** (winners.ca) — ❌ `n/a`: NO online catalog (store-locator/articles only, "shop in-store"). Like Toys R Us. Nothing to scrape.

**General merchandise / marketplace / home**
- Amazon.ca — usable per SKILL.md §8 (his single most-used retailer by far); a fallback, not recon.
- **Walmart CA** (walmart.ca) — ✅ `done` (see recipe). General merch + kids; house brand George is heavily 100% cotton. VPS PerimeterX-walled → Mac CDP with homepage warm-up.
- **Costco CA** — `blocked` (press-and-hold); membership warehouse, his CIBC Costco card.
- **Canadian Tire** (canadiantire.ca) — `wip`: Triangle member; home/auto/seasonal. `web_extract` renders only the shell; products hydrate from Akamai-walled APIM (`apim.canadiantire.ca`) — same FGL/Nucleus stack as Sport Chek/Mark's → Mac CDP Network-intercept needed.
- **IKEA CA** (ikea.ca) — ✅ `done` (see recipe). Furniture, home goods & textiles; frequent. Cloudflare-walled to curl/API → `web_extract` rendered-DOM. Live stock not in render.
- **Indigo / Chapters** (indigo.ca) — ✅ `done` (see recipe). Books & gifts (gift track). Now a Shopify store, NO bot wall, VPS-side. Old `chapters.indigo.ca` retired.
- **Staples CA** (staples.ca) — ✅ `done` (see recipe). Office/tech/home-office (gift/gap-filler). Shopify; `.json`/PDP Cloudflare-walled but `.js` open, pure `urllib` VPS-side.
- **Michaels** (michaels.com) — crafts/gifts. `blocked` (curl-403 on .com and canada.michaels.com; no VPS render path).
- **Party City CA** (partycity.ca) — party/kids events. `blocked` (Akamai on `web_extract`).
- **Toys R Us CA** (toysrus.ca) — ❌ `n/a`: NO online catalog (store-locator/FAQ only, "shop in-store"). Nothing to scrape.
- **RONA** (rona.ca) — home improvement. `blocked` (homepage 200 but PDP DataDome-captcha on `web_extract` + curl-403; needs Mac CDP).

**Beauty / personal care**
- **Deciem / The Ordinary** (theordinary.com) — ✅ `done` (see recipe). Skincare (gift/personal-care). Demandware (NOT Shopify); PDP JSON-LD + static INCI attribute; NO bot wall, VPS-side.
- **The Body Shop CA** — ✅ `done` (see recipe). Beauty/personal-care (gift track). Shopify `.js` + PDP INCI span; NO bot wall, VPS-side.
- **Bath & Body Works CA** — gifts. `blocked` (PerimeterX px-captcha on VPS; needs Mac CDP).

**Specialty / gifts**
- **Brilliant Earth** (brilliantearth.com) — ✅ `done` (see recipe). Fine jewelry (a real past purchase; gift direction). GIFT track — natural-fibre gate N/A. curl→Cloudflare-403 → `web_extract` renders clean first pass; use `/en-ca/` for CAD.
- **EyeBuyDirect** (eyebuydirect.com) — prescription eyewear. `blocked` (redirects to eyebuydirect.ca; PDP Akamai-walled to curl AND `web_extract`; category renders but PDPs return the Akamai shell). Needs Mac CDP.
- **Sephora CA** (sephora.com/ca/en) — ✅ `partial` (see recipe). Prestige beauty (gift track). Product API Akamai-403 from VPS; `web_extract` renders name+list+sale price (image/INCI/stock need Mac CDP).
- **Etsy** — handmade/gifts. `blocked` from VPS (DataDome captcha on `web_extract`, curl-403; the public API needs an OAuth app key). Would need Mac CDP or a registered API key.
- **RONA** (rona.ca) — home improvement. `blocked` (homepage 200 but PDP DataDome-captcha on `web_extract`, PDP curl-403). Needs Mac CDP.

### Other good picks (not confirmed in YNAB, but fit the household)

- **Roots** (roots.com) — ✅ `done` (see recipe). Canadian, heavy organic-cotton fleece; kids + adults; natural-fibre-friendly. No bot wall, VPS-side.
- **Province of Canada** (provinceofcanada.com) — ✅ `done` (see recipe). Canadian, made-in-Canada organic/GOTS-cotton basics (tees, fleece, denim shirts) — strong natural-fibre source. Shopify, NO bot wall, pure `urllib` VPS-side (`.js` price/stock + `.json` body_html composition).
- **Frank And Oak** (frankandoak.com) — ✅ `done` (see recipe). Canadian, cotton/wool/linen/hemp focus, sustainability angle. Shopify, NO bot wall, VPS-side.
- **Oak + Fort** (oakandfort.com) — ✅ `done` (see recipe). Canadian minimalist DTC (women/men); real 100% linen/cotton lines but "Blend" pieces cut in ~45% rayon — read the %. Shopify, NO bot wall, pure `urllib` VPS-side (`.js` price/stock + static "Materials & Care" accordion composition).
- **Naked & Famous Denim** (nakedandfamousdenim.com) — ✅ `done` (see recipe). Montreal premium selvedge denim (men's, some women's); raw jeans 100% cotton, stretch 98/2 cotton/elastane, tees 100% cotton — top men's natural-fibre source. Shopify, NO bot wall, pure `urllib` VPS-side (single `.js` call has price/stock/image AND composition). ⚠️ `.js` has no currency → hard-code CAD; JSON-LD price is USD (wrong for CA).
- **Icebreaker CA** (na.icebreaker.com/en-ca) — ✅ `done` (see recipe). Merino specialist; 100% merino tees/base layers + TENCEL/merino Cool-Lite blends — top natural-fibre source; adult + kids layers. Shopify, NO bot wall, pure `urllib` VPS-side (`.js` price/stock + PDP `<strong>Fabric content</strong>` composition). ⚠️ `/en-ca/` prefix mandatory (else 302→USD); JSON-LD price is stale USD.
- **Unbound Merino** (unboundmerino.com) — ✅ `done` (see recipe). Canada-shipping merino specialist; 100% merino tees/base layers/sleep sets + merino/linen woven shirts — top natural-fibre source (men + women, travel/everyday). Shopify, NO bot wall, pure `urllib` VPS-side (`.js?currency=CAD` price/stock + PDP `ul.product-tab__details-list` composition). ⚠️ store defaults to USD → MUST append `?currency=CAD`; merino socks ~40% nylon fail a 70% gate.
- **tentree** (tentree.ca) — ✅ `done` (see recipe). Canadian sustainable apparel (men/women/kids); organic cotton, hemp, TENCEL. Shopify, NO bot wall, pure `urllib` VPS-side (`.js` price/stock + PDP `fabric-composition` attribute). ⚠️ "TreeBlend" tees are ~45% recycled poly — read the % (TENCEL=natural, recycled poly=synthetic).
- **Mark's** (marks.com) — ✅ `done` (see recipe). Workwear/casual, cotton basics (Denver Hayes/WindRiver). Canadian Tire/FGL stack; VPS Akamai-403 → Mac CDP Network-intercept.
- **Tilley** (tilley.com) — ✅ `done` (see recipe). Canadian natural-fibre travel/outdoor (100% cotton/linen hats + tees). Shopify, NO bot wall, VPS-side.
- **MEC** (mec.ca) — ✅ `done` (see recipe). Outdoor co-op; merino/organic-cotton; Canadian. Headless Next.js over BigCommerce; curl→Cloudflare-403 → `web_extract` rendered-DOM (renders clean first pass). Live stock not in render.
- **Kotn** (kotn.com) — ✅ `done` (see recipe). Canadian, Egyptian-cotton essentials; near-100%-cotton catalog, top natural-fibre source. Next.js front + headless Shopify; NO bot wall, VPS-side.
- **Everlane** (everlane.com) — ✅ `done` (see recipe). US (ships CA); 100% organic-cotton/cashmere/merino/linen essentials — top natural-fibre source. Shopify, NO bot wall, VPS-side. ⚠️ prices in USD.
- **Patagonia CA** (patagonia.ca) — ✅ `partial` (see recipe). Premium outdoor/casual; top organic-cotton/hemp natural-fibre source (adults + kids). SFCC/Demandware; VPS hard-walled (curl→decoy 404, no JSON-LD/Shopify/OCAPI) → `web_extract` rendered-DOM (intermittent, retry). Composition/price YES; **image + per-size stock need Mac CDP**. Tech/fleece lines (Capilene/Nano Puff/Better Sweater) = recycled poly → FAIL the fibre gate; read the %.
- **Quince** (quince.com/ca) — ✅ `done` (see recipe). Affordable-luxury DTC; 100% organic-cotton/cashmere/linen/silk across women/men/kids/home — top natural-fibre source, prices in CAD on `/ca/`. NO bot wall, plain `urllib` VPS-side (JSON-LD + `__NEXT_DATA__`). ⚠️ product names lie about blends (Cotton Modal = 50% modal) — gate on the `%` in `details`.
- **Hudson's Bay** (thebay.com) — ❌ `n/a`: DEFUNCT (closed 2025); thebay.com redirects to canadiantire.ca. No catalog.
- **Mountain Warehouse CA** (mountainwarehouse.com/ca) — ✅ `done` (see recipe). Value outdoor apparel; strong organic-cotton/merino natural-fibre lines. Next.js over BigCommerce; NO bot wall — all fields in the static HTML from a plain `urllib` GET. **Decathlon CA** — ✅ `done` (see recipe). Value sports/outdoor; VPS Cloudflare-walled → Mac CDP (composition hides behind a collapsed Specifications accordion; web_extract only partial).

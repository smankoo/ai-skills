# Cart JSON schema

One file per person. Prices are **numbers**, never strings — the builder sums them so no total
is ever hand-written. Everything else is presentation.

The values below are an illustrative fixture, not anyone's real data. Carts hold a first name and a
context line and nothing more — no addresses, no record numbers, no health information.

```jsonc
{
  "name": "Ada",
  "slug": "01-ada",                        // output filename: email-01-ada.html
  "subtitle": "Junior Kindergarten · size 5T",
  "eyebrow": "Fall 2026 · Shopping Cart",  // optional, defaults to this
  "currency": "$",                          // optional, default "$"
  "expect_total": 467.83,                   // optional; build fails loudly on mismatch

  // Top banner. Use for the size derivation on children.
  "sizebox": [
    ["Size", "<strong>5 YRS / 5T</strong> — ~43 in; the retailer's 5 YRS band is 42–45 in"],
    ["Stores", "Value chain for play clothes · mid-market for the nicer pieces"],
    ["Checked", "Every item confirmed <strong>in stock in 5T</strong> on 4 Aug"]
  ],

  "sections": [
    // A callout block. kind: "info" (green) | "warn" (amber).
    { "type": "note", "kind": "info",
      "text": "<strong>The rule that shaped this list:</strong> she has to dress herself." },

    // A section of purchasable items. Subtotal is computed.
    { "type": "section",
      "title": "Bottoms — 7",
      "blurb": "Seven means laundry runs twice a week without a scramble.",
      "items": [
        { "qty": 2, "name": "Dynamic Fleece Jogger Sweatpants",
          "url": "https://oldnavy.gapcanada.ca/browse/product.do?pid=490929033&vid=1",
          "meta": "Old Navy · buy two different colours",
          "price": 14.99 },
        { "qty": 1, "name": "Wow Straight Pull-On Jeans",
          "url": "https://oldnavy.gapcanada.ca/browse/product.do?pid=422209023&vid=1",
          "meta": "Old Navy · real denim look, elastic waist",
          "price": 12.49 }
      ] },

    // A prose-only section, e.g. "Three outfits this makes".
    { "type": "prose", "title": "Three outfits this makes",
      "body": "<strong>1. Office, 14 °C</strong> — navy oxford + charcoal wool trouser" }
  ],

  "footnote": "23 items across two retailers. One of them is running roughly 50% off.",
  "footer": "Prices captured 4 Aug 2026 and will drift — sale prices especially."
}
```

## Fields

| Field | Required | Notes |
|---|---|---|
| `name` | yes | Shown large in the header |
| `slug` | yes | Drives the output filename |
| `subtitle` | no | Line under the name |
| `expect_total` | no | Guard rail. Build fails if the computed total differs by >$0.01 |
| `sizebox` | no | Array of `[label, html_value]` pairs |
| `sections[].type` | yes | `note` \| `section` \| `prose` |
| `items[].qty` | no | Defaults to 1. `>1` renders a `×N` badge and multiplies into the subtotal |
| `items[].price` | yes | **Number.** A per-unit price; `qty × price` goes into the subtotal |
| `items[].meta` | no | Small grey line under the name — store, colour, fit. May contain HTML |
| `items[].url` | no | Omit for a bundle row whose links live in `meta` |
| `items[].image` | no | Thumbnail URL. Rendered in a fixed 72×96 box, linked to `url`, so the cart is browsable at a glance |

## Getting image URLs

Product images are on the **rendered** category grid, not in the raw HTML — `fetch` returns an
empty shell for Gap/Old Navy category pages. Navigate to the grid, then map pid → image from the
DOM:

```js
(() => {
  const map = {};
  document.querySelectorAll('a[href*="pid="]').forEach(a => {
    const pid = (a.href.match(/pid=(\d+)/) || [])[1];
    if (!pid) return;
    const card = a.closest('[class*="product-card"], [class*="ProductCard"], li');
    const im = card && card.querySelector('img');
    const src = im && (im.currentSrc || im.src);
    if (src && !map[pid]) map[pid] = src;
  });
  return map;
})()
```

`content.gapinc.com` URLs take a `?width=` parameter — use `?width=200` for email thumbnails
rather than the 737px grid version. Do **not** scrape the first `content.gapinc.com` URL out of
a product page's raw HTML: it's often a shared asset, so unrelated items end up sharing one
image. On Amazon, `#landingImage`'s `src` is the reliable per-item image.

Two checks worth running before you send, both of which have caught real problems:

1. **Fetch every URL and confirm it returns `image/*` with a plausible byte count.** A 404 or an
   HTML error page produces a broken thumbnail, which looks worse than no thumbnail at all.
2. **Confirm the images are distinct from each other.** Identical byte counts across rows is the
   signature of the shared-asset mistake above.

Retailers do not agree on aspect ratio — a Gap grid shot is 3:4 while an Amazon full-body shot can
be 1:3. The builder therefore renders into a fixed 72×96 box with `object-fit:contain`, which
letterboxes rather than crops, so the whole garment stays visible and every row keeps the same
height. Don't switch this to `height:auto`: one tall image then stretches its row and the item
column stops lining up.

## Conventions

- `price` is **per unit**. `qty: 2, price: 14.99` renders as `$14.99 ea` and adds `$29.98`.
- Item counts in section titles ("Bottoms — 7") are the *garment* count, which may exceed the
  row count because of `×N` and multipacks. Keep them consistent with the checklist.
- HTML is allowed in `meta`, `blurb`, `body`, `text`, and sizebox values. Item `name` is escaped.
- Use `&mdash;`, `&middot;`, `&deg;` etc. rather than raw characters for mail-client safety.

# Cart JSON schema

One file per person. Prices are **numbers**, never strings — the builder sums them so no total
is ever hand-written. Everything else is presentation.

```jsonc
{
  "name": "Tegh",
  "slug": "01-tegh",                       // output filename: email-01-tegh.html
  "subtitle": "Junior Kindergarten · size 5T",
  "eyebrow": "Fall 2026 · Shopping Cart",  // optional, defaults to this
  "currency": "$",                          // optional, default "$"
  "expect_total": 467.83,                   // optional; build fails loudly on mismatch

  // Top banner. Use for the size derivation on children.
  "sizebox": [
    ["Size", "<strong>5 YRS / 5T</strong> — he's ~43 in; Gap's 5 YRS band is 42–45 in"],
    ["Stores", "Old Navy for play clothes · Gap for the nicer pieces"],
    ["Checked", "Every item confirmed <strong>in stock in 5T</strong> on 4 Aug"]
  ],

  "sections": [
    // A callout block. kind: "info" (green) | "warn" (amber).
    { "type": "note", "kind": "info",
      "text": "<strong>The rule that shaped this list:</strong> he has to dress himself." },

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

  "footnote": "23 items across Gap and Old Navy. Old Navy is running roughly 50% off.",
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

## Conventions

- `price` is **per unit**. `qty: 2, price: 14.99` renders as `$14.99 ea` and adds `$29.98`.
- Item counts in section titles ("Bottoms — 7") are the *garment* count, which may exceed the
  row count because of `×N` and multipacks. Keep them consistent with the checklist.
- HTML is allowed in `meta`, `blurb`, `body`, `text`, and sizebox values. Item `name` is escaped.
- Use `&mdash;`, `&middot;`, `&deg;` etc. rather than raw characters for mail-client safety.

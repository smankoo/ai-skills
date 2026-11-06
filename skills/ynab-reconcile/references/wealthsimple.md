# Wealthsimple as the "bank file" (no CSV needed)

Use this instead of asking Sumeet for an export. Log in on the iMac Chrome with the browser-ops recipe
(`login_fill_cdpx.sh`, then TOTP from 1Password, then a trusted-device "Yes" that Sumeet taps in the WS app).
Then read the data straight from WS's own GraphQL API, inside the logged-in tab.

- **Auth.** Cookie `_oauth2_access_v2` is URL-encoded JSON: `access_token` and `identity_canonical_id`. Send it to
  `POST https://my.wealthsimple.com/graphql` with the headers `authorization: Bearer …`, `x-ws-profile: trade`,
  `x-ws-api-version: 12`.
- **Don't hand-write the activity query.** Public ws-api query shapes get `UNPROCESSABLE_ENTITY`. Instead:
  1. Monkey-patch `window.fetch` to record graphql bodies.
  2. Route the SPA without reloading: `history.pushState({},'','/app/activity?account_ids=<id>')` plus a `popstate` event.
  3. Replay the captured `FetchActivityFeedItems` that has `condition.types`. Delete `types`, set `accountIds`,
     `startDate` and `endDate`, `first: 100`, and page with `cursor`.
- **Fields.** `amount` is unsigned; the direction is in `amountSign` (positive/negative). `unifiedStatus` is
  COMPLETED or PENDING. The description comes from `spendMerchant`, `eTransferName` or `subType`.
- **Balances.** `query { accounts(ids:[…]) { id financials { currentCombined { netLiquidationValueV2 { amount } } } } }`
  works for cash accounts. For the credit card it returns 0, so read "Settled" and "Pending" from
  `/app/account-details/<card-id>`.
- **Account ids (Sumeet):** chequing `ca-cash-msb-h6jU0XgrEw`, Mummy Papa Cash `ca-cash-msb-qg6W7YIC4w`, card
  `ca-credit-card-giEBLRI8cQ`.

## Lessons from the 2026-11-01 reconcile
- **The YNAB WS feeds silently drop whole date windows.** The card lost Aug 21–25 purchases while the payments still
  imported. Cash lost Sep 1–21, so 19 manual card-payment sides sat uncleared. Match by amount multiset over a window,
  then list the bank-only items for each unmatched day.
- **Multiset matching can pair a YNAB item with the wrong-date bank twin.** Before adding a "missing" item, list
  every bank and YNAB row for that amount.
- **Interac e-Transfers from Priyanka land in WS Cash, not BMO.** YNAB's auto-transfer matching guessed BMO twice.
- **$0.01 "Hangtag" style pre-auths import into YNAB but never settle.** Delete them.
- **The API can mark transactions `reconciled`, but it doesn't move `last_reconciled_at`.** That's cosmetic.

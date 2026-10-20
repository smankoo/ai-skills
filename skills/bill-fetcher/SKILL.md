---
name: bill-fetcher
description: "Use when a 'your bill is ready' email arrives without the PDF, or when adding a new biller. Logs in, downloads the bill PDF, files it in Google Drive › Bills & Receipts, and emails it back as a threaded reply."
version: 1.0.0
metadata:
  hermes:
    tags: [bills, email, automation, pdf, icloud-drive]
    related_skills: [browser-ops, email-correspondence, pebbleway]
---

# Bill fetcher

The user hates bill notices that make him log in to a vendor site. The job: when one arrives, sign in,
download the bill PDF, file it, and email it back to him **as a reply on the same thread**.

## Pipeline (cron "Bill fetcher")

1. **Collector**: `~/.hermes/scripts/bill_watch_collect.py [days=3]` (copy in `scripts/`). It is read-only. It scans
   the icloud, gmail and proton himalaya accounts for known vendor notices (the `VENDORS` table), skips
   anything already in `~/.hermes/bills/ledger.jsonl`, and prints one JSON line per pending notice or
   `NO_PENDING_BILLS`. It is wired as the cron **monitor**, so the agent only wakes when something changed.
2. **Fetch**: one browser_exec session named `bills`. Credentials come from 1Password vault "Home Servers"
   via `op item get <item> --fields username/password --reveal` inside the browser_exec code, filled with
   `fill_input`. **Never print them.** SMS or email OTPs: read them yourself with `imac_sms_read.py --code` or
   himalaya. Never ask another agent to relay them.
3. **Verify** the bytes start with `%PDF`. Extract amount, due date and bill date from page 1 (PyMuPDF `fitz`).
4. **File** to Google Drive. This is the PRIMARY home (Sumeet, 2026-10-13: "store them in the appropriate folder").
   Use `0 PARA/2 Areas/Bills & Receipts/<Category>/<Vendor>/<YYYY-MM-DD>_<vendor-slug>_<amount>.pdf`,
   which matches his existing files (e.g. `Utilities/Cogeco/2026-04-11_cogeco_67.79.pdf`). Categories in use:
   `Utilities` (Enercare, Enbridge, Hydro, Cogeco, Rogers, Fido), `Banking` (cards). For a new category
   (e.g. cloud/hosting: OVH, AWS, Cloudflare), propose the name to Sumeet once and reuse it after.
   `python3 ~/.hermes/scripts/gdrive_write.py mkdir "<folder>"` (if new), then
   `python3 ~/.hermes/scripts/gdrive_write.py upload bill.pdf "<folder>" --name "<file>"`, then `ls` to verify.
   (That prefix was allow-listed in `~/.config/gdrive-write/allow.txt` on 2026-10-13.)
   iCloud Drive › Bills (on the iMac) is legacy. Only Enercare 2026-10-08 is there, and it's been copied to Drive.
5. **Email**: `~/.hermes/scripts/bill_send.py --account <acct> --orig-id <id> --pdf ... --vendor ... --amount
   --due --bill-date --saved-to "Google Drive › Bills & Receipts › <Category> › <Vendor>"`. It replies to the original notice
   (In-Reply-To/References from `himalaya message read --raw`) and attaches the PDF. Use `--dry-run` first on a
   new vendor.
6. **Ledger**: append `{key, vendor, bill_date, amount, due, invoice, file, gdrive, emailed, at}` to the ledger.
7. **Pebbleway (Sumeet, 2026-10-13: "pebbleway is such a natural home for bills… proper links and metadata").**
   Every bill becomes ONE linked, attached Thing:
   `python3 ~/.hermes/scripts/bill_to_pebbleway.py --vendor <V> --service-name "<service/utility node name>"
   --pdf <file> --amount <a> --due <YYYY-MM-DD> --bill-date <YYYY-MM-DD> [--invoice] [--account-number]
   [--period] --gdrive-path "<Drive path from step 4>" --email-key <ledger key>` (`--dry-run` first on a new vendor).
   - It creates or UPDATES an `event` "<Vendor> bill: $<amt>, due <date>" with `event_type:due`, amount, dates,
     invoice/account numbers, billing period, `gdrive_path` + `gdrive_url` (file id looked up automatically),
     `email_key`, and `status:open`. It reuses an earlier "bill ready" event for the same vendor, due date and amount.
   - Edges: `event_for` → the service/utility node; `paid_with` → that service's card (copied from the service's
     own `paid_with` edge); `related_to` → the vendor `place` if one exists.
   - Attaches the PDF (copied to `~/.hermes/bills/files/` first so the attachment never points at /tmp).
   - Service node names in use: "Enercare (Hot Water / HVAC)", "Enbridge Gas (Burlington)", "Cogeco Internet
     (Burlington)", "Burlington Hydro Electricity", "Phone Plans (Fido/Rogers)".
   - Once paid (YNAB shows it), set `status:paid`, `paid_on`, and `event_type:custom` with `original_event_type:due`.
     Otherwise the attention list keeps showing it as overdue (see the pebbleway skill).
   - **Pitfall:** hop-1 `expand` on an event hides its `event_for` edge. Check edges with
     `query_graph {kind:"induced", node_ids:[...]}`. `patch_graph` has NO dry-run flag, so a "test" add is a REAL
     write (2026-10-13: three stray edges had to be deleted).

## Vendor recipes (verified dates)

| Vendor | Status | How |
|---|---|---|
| **Enercare** (2026-10-09 ✅) | ready | `myaccount.enercare.ca`, Azure B2C login: `#signInName`, `#password`, `#next`. Go to `/billing?account=<acct>`. Each bill row's download button `[data-testid=billing-history-invoice-download-btn]` calls `GET /api/billing/invoice/download?invoiceId=…&accountNo=…&transactionId=INV…&date=<Mon+D%2C+YYYY>`, which returns `application/pdf` directly. Same-origin `fetch()` → base64 → bytes. Get the invoiceId by clicking the row's button and reading `performance.getEntriesByType('resource')`. |
| **Cogeco** (2026-10-13 ✅) | ready | The ForgeRock XUI login page (`customer-services.cogeco.ca/am/XUI`) can render "Unable to login." with no form, so skip the UI. On that origin, POST `/am/json/realms/root/realms/myaccount/authenticate?locale=en&authIndexType=service&authIndexValue=login` (headers `Content-Type: application/json`, `Accept-API-Version: resource=2.1, protocol=1.0`, body `{}`). Fill `callbacks[0]` (username) and `callbacks[1]` (password), then POST it back to get a tokenId cookie. Next, goto `/am/oauth2/authorize?client_id=ccx-mya-web&scope=myaccount&response_type=code&redirect_uri=https://myaccount.cogeco.ca/callback&service=login&ui_locales=en`. If `myaccount.cogeco.ca` shows a Cloudflare "security verification" page, click the Turnstile iframe (AX name "Widget containing a Cloudflare security challenge") at x+30, then `Page.reload`. Billing is at `/acauth/all/billing`. The first `button` with text "Download" is the newest invoice. It fetches `/api/ext/v2/accounts/<acct>/documents/<docId>/pdf?origin=SYMCOR` (application/pdf). Use `Browser.setDownloadBehavior` to save it. Page 1 has the total, due date and invoice number; page 2 has the billing period. Use `pdftotext` (fitz isn't installed for system python3). |
| OVHcloud | 1P item exists, untested | ca.ovh.com control panel › Billing; also has an API (blocked: "Incompatible country") |
| AWS | 1P item ambiguous | confirm which AWS item is the billed account before use |
| **Burlington Hydro** (2026-10-20 ✅) | ready | 1P item `Burlingtonhydro`. `myaccount.burlingtonhydro.com/page/login` (Angular Material). `fill_input` does NOT register: set `#mat-input-0` (email) / `#mat-input-1` (password) via the native value setter + `input`/`change`/`blur` events, then click the button with text "SIGN IN". Lands on `/myaccount/myaccount#!/billings/<acct>`. The API is cross-origin with a bearer token (`myaccountapi-dot-bhi-myaccount-prod.appspot.com/api/v1/...`), so don't `fetch()` it yourself: `Browser.setDownloadBehavior` then click the UI. Newest bill: anchor "View Current Bill" (calls `/accounts/<acct>/invoice/lastBillPdf`). Older bills: `location.hash='#!/mybills/<acct>'`, then the Nth "VIEW BILL" anchor (`/invoice/billPdf?invoiceId=…`), ~8 s apart. File = `Invoice_<acct>_<invoice>_<YYYY-MM-DD>.pdf`. `pdftotext -layout`: electricity is MONTHLY (`Previous: … Present: … Consumption:`), Halton water is BI-MONTHLY and only on every other bill; the water header says "Estimated" when the read was estimated. Water page `#!/wateruse/<acct>/<svc>` only has per-bill totals (no interval data). Payment is bank PAP (no card edge). |
| Enbridge Gas, Rogers, Fido, Cloudflare | waiting on a 1P login from the user | — |
| Banks/cards (BMO, TD, Tangerine, Scotia, Wealthsimple) | optional; user to decide | expect SMS MFA on every login |

**Add a recipe the same day you get a new vendor working** (selectors, download endpoint, gotchas), per
browser-ops rules.

## Rules
- Only fetch for vendors in the table. Never pay a bill, change autopay, or change a card or billing setting.
  Surface "payment method expiring" banners in the report instead (e.g. Enercare showed a card expiring 11/2026).
- One email per bill. If a download fails twice, report it in one line and leave it out of the ledger so it retries.
- Never put account numbers or email addresses into this skill (PII CI).

## Updating a biller's card on file (verified Enercare 2026-10-11)
Sumeet has approved moving bills to the **Wealthsimple Visa ••5176** (1Password "Home Servers" › "Wealthsimple Credit Card"). It's a card swap, not a payment, so do it rather than reporting "card expiring". Read the card fields from `op item get … --reveal` inside the same call; never print them.
- **Enercare:** go to `/billing/payments/autopay?account=<acct>&action=update`. Click the "Update payment method" card (a div with an onclick, reached through its text node's parent ×3). Choose "Credit card or debit card", click Next, tick the `#update-terms` checkbox, click Next. Then fill the **Zuora hosted page** iframe, which is cross-origin: `Target.attachToTarget` on the `na.zuora.com/apps/PublicHostedPageLite.do` target, then `Runtime.evaluate` with `session_id`.
  - ⚠️ Setting `.value` + events leaves the fields "filled", but submit fails with **`{Error: BIL005014}` "check your internet connection"**. Zuora needs **real keystrokes**: `Input.dispatchKeyEvent` keyDown/keyUp per char with `session_id` for the number, CVV and name. Set the selects for month/year. Click Submit.
  - Verify on reload: "Payment method: Visa ending in 5176". Then update the Pebbleway utility node (`payment_method` property plus a `paid_with` edge: patch_graph `add_edges` uses keys `from`/`to`/`rel_type`).

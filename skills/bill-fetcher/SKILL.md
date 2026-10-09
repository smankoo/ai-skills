---
name: bill-fetcher
description: "Use when a 'your bill is ready' email arrives without the PDF, or when adding a new biller. Logs in, downloads the bill PDF, files it in iCloud Drive › Bills, and emails it back as a threaded reply."
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
4. **File** to iCloud Drive on the iMac. The VPS can't write there, and scp chokes on the space in the path,
   so pipe the file instead:
   `ssh sumeet@<imac> 'cat > "$HOME/Library/Mobile Documents/com~apple~CloudDocs/Bills/<Vendor>/<YYYY-MM-DD> <Vendor> <amount>.pdf"' < bill.pdf`
   (`mkdir -p` the vendor folder first.)
5. **Email**: `~/.hermes/scripts/bill_send.py --account <acct> --orig-id <id> --pdf ... --vendor ... --amount
   --due --bill-date --saved-to "iCloud Drive › Bills › <Vendor>"`. It replies to the original notice
   (In-Reply-To/References from `himalaya message read --raw`) and attaches the PDF. Use `--dry-run` first on a
   new vendor.
6. **Ledger**: append `{key, vendor, bill_date, amount, due, invoice, file, emailed, at}` to the ledger.
   Then record it in Pebbleway (bill amount + due date on the vendor/account node).

## Vendor recipes (verified dates)

| Vendor | Status | How |
|---|---|---|
| **Enercare** (2026-10-09 ✅) | ready | `myaccount.enercare.ca`, Azure B2C login: `#signInName`, `#password`, `#next`. Go to `/billing?account=<acct>`. Each bill row's download button `[data-testid=billing-history-invoice-download-btn]` calls `GET /api/billing/invoice/download?invoiceId=…&accountNo=…&transactionId=INV…&date=<Mon+D%2C+YYYY>`, which returns `application/pdf` directly. Same-origin `fetch()` → base64 → bytes. Get the invoiceId by clicking the row's button and reading `performance.getEntriesByType('resource')`. |
| Cogeco | 1P item exists, untested | myaccount.cogeco.ca |
| OVHcloud | 1P item exists, untested | ca.ovh.com control panel › Billing; also has an API (blocked: "Incompatible country") |
| AWS | 1P item ambiguous | confirm which AWS item is the billed account before use |
| Enbridge Gas, Burlington Hydro, Rogers, Fido, Cloudflare | waiting on a 1P login from the user | — |
| Banks/cards (BMO, TD, Tangerine, Scotia, Wealthsimple) | optional; user to decide | expect SMS MFA on every login |

**Add a recipe the same day you get a new vendor working** (selectors, download endpoint, gotchas), per
browser-ops rules.

## Rules
- Only fetch for vendors in the table. Never pay a bill, change autopay, or change a card or billing setting.
  Surface "payment method expiring" banners in the report instead (e.g. Enercare showed a card expiring 11/2026).
- One email per bill. If a download fails twice, report it in one line and leave it out of the ledger so it retries.
- Never put account numbers or email addresses into this skill (PII CI).

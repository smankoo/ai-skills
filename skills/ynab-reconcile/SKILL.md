---
name: ynab-reconcile
description: >
  Reconcile YNAB accounts against downloaded bank data (OFX/CSV/screenshots) to make
  YNAB reflect reality -- find phantom/duplicate/miscategorized/missing transactions,
  fix them via the API, and close the residual with an in-app Reconcile. Use when the
  user says their YNAB numbers look wrong/off/"all over the place", asks to reconcile,
  or drops a folder of bank exports.
---

# YNAB Reconciliation

Goal: make each YNAB account balance equal the real bank balance, transaction by
transaction, then let YNAB book a Reconciliation Balance Adjustment for any tiny
unexplained residual. Only touch the accounts the user asks about -- if multiple
people share a budget, others reconcile their own accounts.

This skill carries no one's account list, credentials, or categorization rules. If the
project has its own conventions file (account names, category rules, credential
location), read it first -- it's the *reference data*; this skill is the *procedure*.

## Setup

1. **Credentials**: set `YNAB_TOKEN` (Personal Access Token, from YNAB > Account
   Settings > Developer Settings) and `YNAB_BUDGET` (the budget UUID, or `last-used` /
   `default`) in the environment. Never hardcode a token into a script that gets saved
   to disk.
2. Use the helper module, not raw curl (see "Environment gotchas"):
   `scripts/ynab_api.py`. It exposes `call(path, method, body)`, `txns(account_id,
   since)`, and a CLI: `python3 ynab_api.py <account_id> <since_date>`.
3. `scripts/reconcile.py` does the heavy lifting: parse a bank file, fetch YNAB
   txns, multiset-match by amount (dates only disambiguate), print the exact
   discrepancy lists + the balance target. Run it before proposing any change:
   `python3 reconcile.py <account_id> <bank_file> [--start YYYYMMDD] [--end YYYYMMDD]`.
   - For **OFX credit-card exports** that start mid-history, pass `--start` = the
     statement's first posting date (the script defaults to the min bank date, which
     is usually right).
   - For an **account newer than the bank export** (has a YNAB "Starting Balance"),
     set `--start` to ~1 day before the account creation date so the items YNAB
     pulled forward onto the creation day (bank-dated the day before) still match.
     Anything left unmatched should be just the Starting Balance row itself.

## Procedure

1. **Inventory the download.** `ls` the folder. Expect OFX (`.ofx`), CSV exports, and
   possibly screenshots of bank/brokerage dashboards. Read the screenshots for the
   *authoritative current balance* of each account -- that's the target number.
2. **Get YNAB account balances:** loop `GET /accounts`. Note `balance`,
   `cleared_balance`, `uncleared_balance`, and `last_reconciled_at` per account.
3. **Per account, match YNAB against the bank file** with `reconcile.py`. It reports:
   - **Bank-not-in-YNAB** -> real transactions to *add* (categorize per the user's own
     conventions).
   - **YNAB-not-on-bank** -> *phantoms/duplicates to delete* OR *real-but-pending* OR
     *posted-before-the-statement-window* (see gotchas -- do NOT blindly delete these).
   - **Amount mismatches** (same payee, wrong amount) -> *edit* the amount.
4. **Classify each YNAB-not-on-bank item** carefully. It is only a phantom if it's
   genuinely not a real charge. Common legit reasons it's absent from the bank file:
   pending (not yet posted), charged to a *different* account, or dated outside the
   statement's date range.
5. **Show the user the proposed changes and the resulting balance before writing.**
   Confirm ambiguous ones (especially anything that looks like a phantom).
6. **Make the writes** via the API (DELETE / PUT amount / POST new). Re-fetch balances
   to verify each account matches (target ± the known residual).
7. **Residual on budget accounts:** never POST a manual "Reconciliation Balance
   Adjustment" -- the API can't create the real thing and a fake one is wrong. Tell the
   user to click **Reconcile** in the YNAB app and enter the bank balance; YNAB books
   the proper adjustment. Confirm afterward via `last_reconciled_at`.

## Environment gotchas (do NOT rediscover these)

- **Shells don't reliably word-split variables** (notably zsh, by default). `for x in
  "$a $b $c"; do set -- $x; ...` can silently yield empty positional args. Don't build
  loops that rely on splitting a string of fields. Write a Python helper instead --
  this is why `ynab_api.py` exists.
- **Don't pipe a token through a shell var into `curl` inside a loop** for the same
  reason; a request can come back empty and JSON parsing will blow up. Use
  `ynab_api.py`.

## Analysis gotchas (the false paths that waste time)

- **Statement date-window boundary is the #1 trap.** An OFX/CSV export often starts
  *later* than the account's last activity in YNAB (e.g. a card's OFX begins mid-month
  but YNAB had cleared items from a week earlier). Those pre-window YNAB items are
  **not phantoms** -- they're part of the bank's *opening* balance for the statement.
  Match only within `[statement_start, statement_end]`; anchor the opening balance as
  `bank_ledger_balance − sum(statement_txns)`. Trying to subset-sum pre-window items as
  phantoms wastes time and risks deleting real transactions.
- **Anchor from the last reconciled point, not account start.** Reconciled items are
  locked-correct. `implied_post_reconcile_activity = current_bank_balance −
  reconciled_sum`; compare that to YNAB's `cleared + uncleared` sum. The gap is the
  error to hunt.
- **Starting Balance boundary (accounts newer than the bank export).** A YNAB account's
  "Starting Balance" folds in everything before its creation date. The bank export may
  reach further back. Verify with a running-balance check:
  `starting_balance` should equal `bank_completed_balance_at_creation − (explicit
  YNAB line items dated on the creation day)`. A running-balance check is what proves
  which side an ambiguous same-day item belongs on.
- **Pending items explain balance diffs -- don't delete them.** Bank "Pending" rows
  aren't in the bank's *completed/ledger* balance. And a real YNAB charge that hasn't
  posted yet makes YNAB legitimately differ from the bank by exactly that amount. If
  `YNAB − bank == a single pending item`, the account is *correct*; leave it and skip
  the reconcile.
- **Robust matcher = multiset by amount, ignoring dates**, then use a small date
  tolerance (±~8 days) only to disambiguate duplicate amounts near the window edge.
  Bank posting dates lag YNAB transaction dates by a few days.
- **`import_id` tells you the origin.** `import_id=YNAB:<amt>:<date>:<n>` = imported
  from the bank. `import_id=None` = manually entered. A duplicate is typically one
  imported + one manual of the same amount; keep the imported one, delete the manual.
  A manual entry with no bank match is the prime phantom suspect (but classify first).
- **Credit-card sign convention:** negative balance = money owed; positive = credit /
  overpayment (they owe you). A bank statement showing a balance in parentheses is
  often a credit -- check the institution's convention.
- **Category substring trap:** never rely on substring matching for categories (e.g. a
  generic "Gas" filter matching a utility named "... Gas Company"). Fetch `GET
  /categories` and use the exact `category_id` UUID when adding transactions.

## Worked example (anonymized, illustrative only)

Given: a chequing OFX, a credit-card OFX (starting mid-month), a second card's CSV
(starting a few months back), and dashboard screenshots.

- **Chequing**: all bank txns matched YNAB to the penny -> no action.
- **Credit card A** (bank total X vs YNAB total Y, a few hundred apart): deleted a
  duplicate charge (manual dup of a bank import) and another charge that actually
  belonged on a different account; edited one amount that had drifted; added several
  real charges missing from YNAB. A small residual remained (a phantom in the
  pre-statement window that wasn't visible) -> the user clicked Reconcile and YNAB
  booked the adjustment.
- **Credit card B** (bank completed balance vs YNAB, off by roughly the size of one
  pending charge): deleted a phantom entry that a running-balance check proved wasn't
  on the statement. Left a real-but-pending charge in place -> YNAB balance now equals
  bank balance plus the pending amount. No reconcile needed.

The residual you can't pin usually lives in a window the export doesn't cover -- if
the user wants it traced instead of adjusted, ask for a statement reaching back
further, with a running balance.

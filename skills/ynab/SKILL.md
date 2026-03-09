---
name: ynab
description: >
  Complete YNAB (You Need A Budget) integration via the YNAB API. Use this skill whenever the user
  mentions YNAB, their budget, spending, transactions, categories, accounts, payees, or anything
  related to personal finance tracking in YNAB. This includes: querying account balances, looking
  up transactions, analyzing spending patterns, creating or updating transactions, checking budget
  category balances, managing scheduled transactions, reviewing monthly budgets, comparing spending
  across months, finding recurring expenses, and any other interaction with YNAB data. Also trigger
  when the user references budget categories, payee names, or financial accounts by name — even if
  they don't explicitly say "YNAB". If the user has previously provided a YNAB token in the
  conversation, treat any personal finance question as a YNAB query.
---

# YNAB Integration

This skill gives you full read/write access to a user's YNAB budget via the YNAB API. You can
query anything, create transactions, update budgets, and perform analytical workflows that go
beyond what the YNAB app itself offers.

## Authentication

The user must provide two things:
1. **Personal Access Token** — created at YNAB > Account Settings > Developer Settings
2. **Budget ID** — a UUID identifying which budget to work with (or use `last-used` / `default`)

If the user hasn't provided these in the current conversation, ask for them. Store them in shell
variables for reuse:

```bash
TOKEN="<their token>"
BUDGET="<their budget id>"
```

Never hardcode tokens into scripts that get saved to disk. Keep them in shell variables or pass
them as arguments.

## Quick Start — The Helper Script

This skill bundles `scripts/ynab_client.py`, a Python helper that handles auth, pagination,
error handling, rate limiting, and milliunit conversion. For any YNAB operation, prefer using
this script over raw curl commands — it handles edge cases and produces clean output.

```bash
# Basic usage pattern
python <skill-path>/scripts/ynab_client.py --token "$TOKEN" --budget "$BUDGET" <command> [options]
```

Read `scripts/ynab_client.py` before first use to see all available commands. The key commands:

### Reading Data
```bash
# Account balances
python ynab_client.py --token "$TOKEN" --budget "$BUDGET" accounts

# All transactions (last 30 days by default)
python ynab_client.py --token "$TOKEN" --budget "$BUDGET" transactions --since 2026-01-01

# Transactions for a specific account, category, or payee
python ynab_client.py --token "$TOKEN" --budget "$BUDGET" transactions --account "BMO Chequing"
python ynab_client.py --token "$TOKEN" --budget "$BUDGET" transactions --category "Grocery"
python ynab_client.py --token "$TOKEN" --budget "$BUDGET" transactions --payee "Amazon"

# Budget categories with balances
python ynab_client.py --token "$TOKEN" --budget "$BUDGET" categories

# Specific month's budget
python ynab_client.py --token "$TOKEN" --budget "$BUDGET" month 2026-03-01

# Payees
python ynab_client.py --token "$TOKEN" --budget "$BUDGET" payees

# Scheduled (recurring) transactions
python ynab_client.py --token "$TOKEN" --budget "$BUDGET" scheduled

# Net worth (all accounts summary)
python ynab_client.py --token "$TOKEN" --budget "$BUDGET" net-worth

# Monthly spending summary
python ynab_client.py --token "$TOKEN" --budget "$BUDGET" spending --months 6
```

### Writing Data
```bash
# Create a transaction
python ynab_client.py --token "$TOKEN" --budget "$BUDGET" create-transaction \
  --account "BMO Chequing" --payee "Coffee Shop" --category "Eating Out" \
  --amount -5.50 --date 2026-03-09 --memo "Morning coffee"

# Update a category's budgeted amount for a month
python ynab_client.py --token "$TOKEN" --budget "$BUDGET" set-budget \
  --category "Grocery" --month 2026-03-01 --amount 1200.00

# Approve a transaction
python ynab_client.py --token "$TOKEN" --budget "$BUDGET" approve-transaction <transaction-id>
```

### Analysis (higher-level workflows)
```bash
# Spending by category over N months (with averages)
python ynab_client.py --token "$TOKEN" --budget "$BUDGET" spending --months 6

# Recurring expense detection (finds payees appearing 3+ times)
python ynab_client.py --token "$TOKEN" --budget "$BUDGET" recurring --months 6

# Income vs expenses summary
python ynab_client.py --token "$TOKEN" --budget "$BUDGET" income-vs-expenses --months 6

# Category trend (spending in one category across months)
python ynab_client.py --token "$TOKEN" --budget "$BUDGET" category-trend --category "Grocery" --months 12
```

## Core Concepts

### Milliunits
All monetary values in the YNAB API are in **milliunits** — thousandths of a currency unit.
`$100.00` = `100000` milliunits. The helper script converts automatically, but if you're
making raw API calls, remember:
- API → display: divide by 1000
- Display → API: multiply by 1000
- Example: user says "$45.99" → send `45990` to the API

### Budget IDs
The `budget_id` path parameter accepts:
- A UUID like `09aeeb2f-203b-4341-840b-68e0251efae9`
- `"last-used"` — the most recently accessed budget
- `"default"` — the user's default budget

### Delta Requests
Many GET endpoints accept `last_knowledge_of_server` (an integer). When provided, the API
returns only entities that changed since that point. Responses include a new `server_knowledge`
value. This is useful for efficient syncing but usually not needed for one-off queries.

### Dates
All dates are ISO 8601 format: `YYYY-MM-DD`. Month endpoints accept `"current"` for the
current UTC month. Future-dated transactions can only be created as scheduled transactions.

### Cleared Status
Transactions have a `cleared` field: `"cleared"`, `"uncleared"`, or `"reconciled"`.
- `uncleared` — entered but not yet confirmed against bank statement
- `cleared` — confirmed against bank statement
- `reconciled` — locked after reconciliation

### Split Transactions
A transaction can be split across multiple categories by including `subtransactions` in the
request body. The parent transaction's `category_id` should be null, and the subtransaction
amounts must sum to the parent amount.

### Transfer Transactions
Transfers between accounts use the target account's `transfer_payee_id` as the `payee_id`.
The API automatically creates the paired transaction in the other account.

## API Rate Limits

200 requests per hour per access token, rolling window. If you hit 429, wait and retry.
The helper script handles this automatically with exponential backoff.

For analytical queries that need lots of data, prefer fetching in bulk (e.g., all transactions
since a date) rather than making many small requests.

## Advanced Workflows

These are things the YNAB app doesn't do natively but that you can accomplish by combining
API calls:

### Spending Pattern Analysis
Pull 6-12 months of transactions, group by payee or category, compute averages, identify
trends, flag anomalies. The `spending`, `recurring`, and `category-trend` commands do this.

### Budget Health Check
Compare budgeted amounts vs actual spending across categories, identify categories that
are consistently over/under budget, calculate "budget accuracy."

### Net Worth Tracking
Sum all account balances (assets minus liabilities) to get net worth. Track across months
by pulling monthly snapshots.

### Payee Consolidation Analysis
Find variations of the same payee name (e.g., "AMZN" vs "Amazon" vs "Amazon.ca") to help
the user clean up their payee list.

### Subscription Detection
Find payees with regular recurring charges at consistent amounts — these are likely
subscriptions the user may want to track or cancel.

### Income Stability Analysis
Analyze income transactions over time to identify patterns, gaps, or changes in income
sources.

### Category Rebalancing
Look at categories with large positive balances (over-budgeted) and categories that
consistently go negative (under-budgeted), suggest reallocations.

For the full API endpoint reference with every field, parameter, and enum, read
`references/api-reference.md`.

## Error Handling

Common API errors:
- `400` — Bad request. Check date formats, milliunit values, required fields.
- `404` — Budget, account, category, or transaction not found. Verify IDs.
- `409` — Conflict, usually a duplicate `import_id`.
- `429` — Rate limited. Wait and retry (the helper script does this automatically).

Error responses have this shape:
```json
{"error": {"id": "...", "name": "...", "detail": "human-readable explanation"}}
```

## Important Notes

- The API uses `"budgets"` and `"plans"` interchangeably in the URL path — both work.
  The OpenAPI spec uses `plans` but most documentation and the user community use `budgets`.
  The helper script uses `budgets` for familiarity.
- Amounts that appear negative in the API represent outflows (spending). Positive amounts are
  inflows (income, refunds, transfers in).
- The `deleted` field appears on almost every entity. Always filter these out unless the user
  specifically asks about deleted items.
- Category balances returned by the categories endpoint are for the **current month** unless
  you use the month-specific endpoint.
- When creating transactions, if you provide a `payee_name` that doesn't exist, YNAB will
  create a new payee automatically. If it matches an existing payee name, it'll use that one.

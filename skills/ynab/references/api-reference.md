# YNAB API v1 — Complete Endpoint Reference

Base URL: `https://api.ynab.com/v1`

Both `/budgets/{id}` and `/plans/{id}` work as path prefixes. This reference uses `/budgets/`.

Auth: `Authorization: Bearer <token>` header on every request.

Rate limit: 200 requests/hour per token (rolling window). 429 response when exceeded.

All monetary amounts are in **milliunits** (1000 = $1.00). Outflows are negative, inflows positive.

---

## User

### GET /user
Returns authenticated user.
```json
{"data": {"user": {"id": "uuid"}}}
```

---

## Budgets

### GET /budgets
List all budgets.
- Query: `include_accounts` (bool)
- Response: `{"data": {"budgets": [...], "default_budget": {...} | null}}`

### GET /budgets/{budget_id}
Full budget export with all entities.
- Path: `budget_id` — UUID, `"last-used"`, or `"default"`
- Query: `last_knowledge_of_server` (int64)
- Response: Full budget detail + `server_knowledge`

### GET /budgets/{budget_id}/settings
Budget settings (currency, date format).
```json
{
  "data": {
    "settings": {
      "date_format": {"format": "DD-MM-YYYY"},
      "currency_format": {
        "iso_code": "CAD", "decimal_digits": 2, "decimal_separator": ".",
        "symbol_first": true, "group_separator": ",", "currency_symbol": "$",
        "display_symbol": true, "example_format": "123,456.78"
      }
    }
  }
}
```

---

## Accounts

### GET /budgets/{budget_id}/accounts
List all accounts.
- Query: `last_knowledge_of_server` (int64)

### POST /budgets/{budget_id}/accounts
Create account.
```json
{"account": {"name": "string", "type": "AccountType", "balance": milliunits}}
```
AccountType enum: `checking`, `savings`, `cash`, `creditCard`, `lineOfCredit`, `otherAsset`,
`otherLiability`, `mortgage`, `autoLoan`, `studentLoan`, `personalLoan`, `medicalDebt`, `otherDebt`

### GET /budgets/{budget_id}/accounts/{account_id}
Single account detail.

### Account fields
| Field | Type | Notes |
|-------|------|-------|
| id | uuid | |
| name | string | |
| type | AccountType | |
| on_budget | bool | |
| closed | bool | |
| note | string? | |
| balance | int64 | milliunits, current available |
| cleared_balance | int64 | milliunits |
| uncleared_balance | int64 | milliunits |
| transfer_payee_id | uuid? | payee ID for transfers TO this account |
| direct_import_linked | bool | linked to bank |
| direct_import_in_error | bool | link is broken |
| last_reconciled_at | datetime? | |
| deleted | bool | |

---

## Categories

### GET /budgets/{budget_id}/categories
All category groups with nested categories. Amounts are for current month.
- Query: `last_knowledge_of_server` (int64)

### POST /budgets/{budget_id}/categories
Create category.

### GET /budgets/{budget_id}/categories/{category_id}
Single category (current month amounts).

### PATCH /budgets/{budget_id}/categories/{category_id}
Update category properties.

### GET /budgets/{budget_id}/months/{month}/categories/{category_id}
Category for specific month.

### PATCH /budgets/{budget_id}/months/{month}/categories/{category_id}
Update budgeted amount for a month.
```json
{"category": {"budgeted": milliunits}}
```
Only `budgeted` is updatable via this endpoint.

### POST /budgets/{budget_id}/category_groups
Create category group.

### PATCH /budgets/{budget_id}/category_groups/{category_group_id}
Update category group.

### Category fields
| Field | Type | Notes |
|-------|------|-------|
| id | uuid | |
| category_group_id | uuid | |
| name | string | |
| hidden | bool | |
| note | string? | |
| budgeted | int64 | assigned amount, milliunits |
| activity | int64 | spending, milliunits (negative = outflow) |
| balance | int64 | available, milliunits |
| goal_type | string? | TB, TBD, MF, NEED, DEBT, null |
| goal_target | int64? | target amount, milliunits |
| goal_target_date | date? | |
| goal_percentage_complete | int? | |
| goal_months_to_budget | int? | months left in period |
| goal_under_funded | int64? | milliunits needed to stay on track |
| goal_overall_funded | int64? | total funded in period |
| goal_overall_left | int64? | milliunits to complete goal |
| deleted | bool | |

---

## Transactions

### GET /budgets/{budget_id}/transactions
All transactions (excludes pending).
- Query: `since_date` (date), `type` ("uncategorized" | "unapproved"), `last_knowledge_of_server` (int64)

### POST /budgets/{budget_id}/transactions
Create one or many transactions. Cannot create future-dated (use scheduled transactions).
```json
// Single
{"transaction": {SaveTransaction}}
// Bulk
{"transactions": [SaveTransaction, ...]}
```

### PATCH /budgets/{budget_id}/transactions
Update multiple transactions. Each needs `id` or `import_id`.

### POST /budgets/{budget_id}/transactions/import
Trigger import from linked financial institutions.

### GET /budgets/{budget_id}/transactions/{transaction_id}
Single transaction with subtransactions.

### PUT /budgets/{budget_id}/transactions/{transaction_id}
Update single transaction.

### DELETE /budgets/{budget_id}/transactions/{transaction_id}
Delete transaction.

### Filtered transaction endpoints
- `GET /budgets/{budget_id}/accounts/{account_id}/transactions`
- `GET /budgets/{budget_id}/categories/{category_id}/transactions`
- `GET /budgets/{budget_id}/payees/{payee_id}/transactions`
- `GET /budgets/{budget_id}/months/{month}/transactions`
All accept: `since_date`, `type`, `last_knowledge_of_server`

### Transaction fields
| Field | Type | Notes |
|-------|------|-------|
| id | string | |
| date | date | ISO 8601 |
| amount | int64 | milliunits, negative = outflow |
| memo | string? | max 500 chars |
| cleared | ClearedStatus | cleared, uncleared, reconciled |
| approved | bool | |
| flag_color | string? | |
| flag_name | string? | |
| account_id | uuid | |
| account_name | string | (in detail responses) |
| payee_id | uuid? | |
| payee_name | string? | (in detail responses) |
| category_id | uuid? | null for splits |
| category_name | string? | "Split" if split |
| transfer_account_id | uuid? | if transfer |
| transfer_transaction_id | string? | paired transfer |
| matched_transaction_id | string? | if matched with import |
| import_id | string? | max 36 chars, format: YNAB:[milliunits]:[date]:[occurrence] |
| import_payee_name | string? | payee name from import |
| import_payee_name_original | string? | original bank statement text |
| debt_transaction_type | string? | payment, refund, fee, interest, escrow, balanceAdjustment, credit, charge |
| subtransactions | array | split details |
| deleted | bool | |

### SaveTransaction (for create/update)
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| account_id | uuid | yes | |
| date | date | yes | no future dates |
| amount | int64 | yes | milliunits |
| payee_id | uuid? | no | use transfer_payee_id for transfers |
| payee_name | string? | no | max 200 chars, auto-resolved |
| category_id | uuid? | no | null for splits |
| memo | string? | no | max 500 chars |
| cleared | ClearedStatus | no | |
| approved | bool | no | |
| flag_color | string? | no | |
| import_id | string? | no | max 36 chars |
| subtransactions | array? | no | for splits |

### SubTransaction (for splits)
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| amount | int64 | yes | milliunits |
| payee_id | uuid? | no | |
| payee_name | string? | no | max 200 chars |
| category_id | uuid? | no | |
| memo | string? | no | max 500 chars |

---

## Scheduled Transactions

### GET /budgets/{budget_id}/scheduled_transactions
All scheduled transactions.
- Query: `last_knowledge_of_server` (int64)

### POST /budgets/{budget_id}/scheduled_transactions
Create scheduled transaction (for future/recurring).

### GET /budgets/{budget_id}/scheduled_transactions/{id}
Single scheduled transaction.

### PUT /budgets/{budget_id}/scheduled_transactions/{id}
Update scheduled transaction.

### DELETE /budgets/{budget_id}/scheduled_transactions/{id}
Delete scheduled transaction.

### ScheduledTransaction fields
Same as Transaction, plus:
| Field | Type | Notes |
|-------|------|-------|
| date_first | date | first occurrence |
| date_next | date | next occurrence |
| frequency | string | never, daily, weekly, everyOtherWeek, twiceAMonth, every4Weeks, monthly, everyOtherMonth, every3Months, every4Months, twiceAYear, yearly, everyOtherYear |

---

## Payees

### GET /budgets/{budget_id}/payees
All payees.
- Query: `last_knowledge_of_server` (int64)

### GET /budgets/{budget_id}/payees/{payee_id}

### PATCH /budgets/{budget_id}/payees/{payee_id}
Update payee name.
```json
{"payee": {"name": "new name"}}
```

### Payee fields
| Field | Type | Notes |
|-------|------|-------|
| id | uuid | |
| name | string | |
| transfer_account_id | uuid? | non-null = transfer payee |
| deleted | bool | |

---

## Payee Locations

### GET /budgets/{budget_id}/payee_locations
### GET /budgets/{budget_id}/payee_locations/{id}
### GET /budgets/{budget_id}/payees/{payee_id}/payee_locations

Fields: `id`, `payee_id`, `latitude`, `longitude`, `deleted`

---

## Months

### GET /budgets/{budget_id}/months
All budget months.
- Query: `last_knowledge_of_server` (int64)

### GET /budgets/{budget_id}/months/{month}
Single month detail with all category breakdowns.
- Path: `month` — ISO date or `"current"`

### Month fields
| Field | Type | Notes |
|-------|------|-------|
| month | date | |
| note | string? | |
| income | int64 | milliunits |
| budgeted | int64 | milliunits |
| activity | int64 | milliunits |
| to_be_budgeted | int64 | milliunits |
| age_of_money | int? | days |
| categories | array | full category detail for this month |
| deleted | bool | |

---

## Money Movements

### GET /budgets/{budget_id}/money_movements
### GET /budgets/{budget_id}/months/{month}/money_movements
### GET /budgets/{budget_id}/money_movement_groups
### GET /budgets/{budget_id}/months/{month}/money_movement_groups

---

## Error Responses

```json
{"error": {"id": "string", "name": "string", "detail": "human-readable"}}
```

| Status | Meaning |
|--------|---------|
| 400 | Bad request / validation error |
| 404 | Resource not found |
| 409 | Conflict (duplicate import_id) |
| 429 | Rate limited (200 req/hr exceeded) |

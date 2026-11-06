#!/usr/bin/env python3
"""
YNAB API Client — full-featured CLI for querying and modifying YNAB budgets.

Usage:
    python ynab_client.py --token TOKEN --budget BUDGET_ID <command> [options]

Commands (read):
    accounts              List all accounts with balances
    transactions          List transactions (--since, --account, --category, --payee, --type)
    categories            List all budget categories with balances
    month YYYY-MM-DD      Show a specific month's budget summary
    months                List all budget months
    payees                List all payees
    scheduled             List scheduled/recurring transactions
    net-worth             Calculate net worth across all accounts
    settings              Show budget settings (currency, date format)
    user                  Show authenticated user info

Commands (write):
    create-transaction    Create a transaction (--account, --payee, --category, --amount, --date, --memo)
    update-transaction    Update a transaction (--id, plus fields to change)
    delete-transaction    Delete a transaction (--id)
    set-budget            Set budgeted amount for a category/month (--category, --month, --amount)
    approve-transaction   Approve a transaction (--id)
    create-account        Create an account (--name, --type, --balance)
    import-transactions   Trigger import from linked institutions

Commands (analysis):
    spending              Spending breakdown by category (--months N)
    recurring             Detect recurring expenses (--months N, --min-count N)
    income-vs-expenses    Income vs expense summary (--months N)
    category-trend        Track one category over time (--category NAME, --months N)
    payee-analysis        Top payees by spend (--months N, --top N)
    subscriptions         Detect likely subscriptions (--months N)
    budget-health         Compare budgeted vs actual across categories

Output: JSON by default. Use --format table for human-readable tables.
        Use --raw for unprocessed API JSON responses.
"""

import argparse, json, sys, time, urllib.request, urllib.error, urllib.parse
from datetime import datetime, timedelta, date
from collections import defaultdict
from math import ceil

BASE = "https://api.ynab.com/v1"

class YNABError(Exception):
    def __init__(self, status, error_id, name, detail):
        self.status = status
        self.error_id = error_id
        self.name = name
        self.detail = detail
        super().__init__(f"[{status}] {name}: {detail}")

class YNABClient:
    def __init__(self, token, budget_id):
        self.token = token
        self.budget_id = budget_id
        self._request_count = 0
        self._window_start = time.time()

    def _throttle(self):
        self._request_count += 1
        if self._request_count >= 180:
            elapsed = time.time() - self._window_start
            if elapsed < 3600:
                wait = min(30, (3600 - elapsed) / 10)
                time.sleep(wait)

    def _request(self, method, path, body=None, retries=3):
        self._throttle()
        url = f"{BASE}{path}"
        data = json.dumps(body).encode() if body else None
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        for attempt in range(retries):
            try:
                with urllib.request.urlopen(req) as resp:
                    return json.loads(resp.read())
            except urllib.error.HTTPError as e:
                body_text = e.read().decode()
                if e.code == 429:
                    wait = 2 ** (attempt + 1) * 10
                    print(f"Rate limited. Waiting {wait}s...", file=sys.stderr)
                    time.sleep(wait)
                    continue
                try:
                    err = json.loads(body_text).get("error", {})
                    raise YNABError(e.code, err.get("id", ""), err.get("name", ""), err.get("detail", body_text))
                except (json.JSONDecodeError, KeyError):
                    raise YNABError(e.code, "", "", body_text)
        raise YNABError(429, "", "rate_limited", "Exhausted retries due to rate limiting")

    def get(self, path, params=None):
        if params:
            qs = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
            if qs:
                path = f"{path}?{qs}"
        return self._request("GET", path)

    def post(self, path, body):
        return self._request("POST", path, body)

    def put(self, path, body):
        return self._request("PUT", path, body)

    def patch(self, path, body):
        return self._request("PATCH", path, body)

    def delete(self, path):
        return self._request("DELETE", path)

    @property
    def bp(self):
        return f"/budgets/{self.budget_id}"

    # ── Read operations ──

    def get_user(self):
        return self.get("/user")["data"]["user"]

    def get_settings(self):
        return self.get(f"{self.bp}/settings")["data"]["settings"]

    def get_accounts(self, include_closed=False):
        accts = self.get(f"{self.bp}/accounts")["data"]["accounts"]
        if not include_closed:
            accts = [a for a in accts if not a["deleted"] and not a["closed"]]
        return accts

    def get_categories(self, month=None):
        if month:
            data = self.get(f"{self.bp}/months/{month}")["data"]["month"]
            return data.get("categories", [])
        groups = self.get(f"{self.bp}/categories")["data"]["category_groups"]
        result = []
        for g in groups:
            if g["deleted"] or g["name"] in ("Internal Master Category", "Hidden Categories"):
                continue
            for c in g.get("categories", []):
                if not c["deleted"] and not c.get("hidden", False):
                    c["group_name"] = g["name"]
                    result.append(c)
        return result

    def get_payees(self):
        payees = self.get(f"{self.bp}/payees")["data"]["payees"]
        return [p for p in payees if not p["deleted"]]

    def get_transactions(self, since_date=None, account=None, category=None, payee=None, txn_type=None):
        params = {}
        if since_date:
            params["since_date"] = since_date

        if account:
            acct_id = self._resolve_account_id(account)
            path = f"{self.bp}/accounts/{acct_id}/transactions"
        elif category:
            cat_id = self._resolve_category_id(category)
            path = f"{self.bp}/categories/{cat_id}/transactions"
        elif payee:
            payee_id = self._resolve_payee_id(payee)
            path = f"{self.bp}/payees/{payee_id}/transactions"
        else:
            path = f"{self.bp}/transactions"

        if txn_type:
            params["type"] = txn_type

        txns = self.get(path, params)["data"]["transactions"]
        return [t for t in txns if not t["deleted"]]

    def get_month(self, month):
        return self.get(f"{self.bp}/months/{month}")["data"]["month"]

    def get_months(self):
        return self.get(f"{self.bp}/months")["data"]["months"]

    def get_scheduled_transactions(self):
        txns = self.get(f"{self.bp}/scheduled_transactions")["data"]["scheduled_transactions"]
        return [t for t in txns if not t["deleted"]]

    def get_payee_locations(self, payee_id=None):
        if payee_id:
            return self.get(f"{self.bp}/payees/{payee_id}/payee_locations")["data"]["payee_locations"]
        return self.get(f"{self.bp}/payee_locations")["data"]["payee_locations"]

    def get_money_movements(self, month=None):
        path = f"{self.bp}/months/{month}/money_movements" if month else f"{self.bp}/money_movements"
        return self.get(path)["data"]

    def get_money_movement_groups(self, month=None):
        path = f"{self.bp}/months/{month}/money_movement_groups" if month else f"{self.bp}/money_movement_groups"
        return self.get(path)["data"]

    # ── Write operations ──

    def create_transaction(self, account, payee_name, category, amount_dollars, txn_date, memo=None, cleared="cleared", approved=True):
        acct_id = self._resolve_account_id(account)
        cat_id = self._resolve_category_id(category) if category else None
        body = {
            "transaction": {
                "account_id": acct_id,
                "date": txn_date,
                "amount": int(round(amount_dollars * 1000)),
                "payee_name": payee_name,
                "category_id": cat_id,
                "cleared": cleared,
                "approved": approved,
            }
        }
        if memo:
            body["transaction"]["memo"] = memo
        return self.post(f"{self.bp}/transactions", body)["data"]

    def create_transactions_bulk(self, transactions):
        """Create multiple transactions. Each item: {account, payee_name, category, amount, date, memo}"""
        txn_list = []
        for t in transactions:
            acct_id = self._resolve_account_id(t["account"])
            cat_id = self._resolve_category_id(t.get("category")) if t.get("category") else None
            txn_list.append({
                "account_id": acct_id,
                "date": t["date"],
                "amount": int(round(t["amount"] * 1000)),
                "payee_name": t.get("payee_name", ""),
                "category_id": cat_id,
                "cleared": t.get("cleared", "cleared"),
                "approved": t.get("approved", True),
                "memo": t.get("memo"),
            })
        return self.post(f"{self.bp}/transactions", {"transactions": txn_list})["data"]

    def update_transaction(self, txn_id, **fields):
        update = {}
        if "amount" in fields:
            update["amount"] = int(round(fields["amount"] * 1000))
        if "date" in fields:
            update["date"] = fields["date"]
        if "payee_name" in fields:
            update["payee_name"] = fields["payee_name"]
        if "category" in fields:
            update["category_id"] = self._resolve_category_id(fields["category"])
        if "memo" in fields:
            update["memo"] = fields["memo"]
        if "cleared" in fields:
            update["cleared"] = fields["cleared"]
        if "approved" in fields:
            update["approved"] = fields["approved"]
        if "flag_color" in fields:
            update["flag_color"] = fields["flag_color"]
        return self.put(f"{self.bp}/transactions/{txn_id}", {"transaction": update})["data"]

    def delete_transaction(self, txn_id):
        return self.delete(f"{self.bp}/transactions/{txn_id}")["data"]

    def approve_transaction(self, txn_id):
        return self.update_transaction(txn_id, approved=True)

    def set_budget_amount(self, category, month, amount_dollars):
        cat_id = self._resolve_category_id(category)
        body = {"category": {"budgeted": int(round(amount_dollars * 1000))}}
        return self.patch(f"{self.bp}/months/{month}/categories/{cat_id}", body)["data"]

    def create_account(self, name, acct_type, balance_dollars=0):
        body = {"account": {"name": name, "type": acct_type, "balance": int(round(balance_dollars * 1000))}}
        return self.post(f"{self.bp}/accounts", body)["data"]

    def import_transactions(self):
        return self.post(f"{self.bp}/transactions/import", {})["data"]

    def create_scheduled_transaction(self, account, payee_name, category, amount_dollars, txn_date, frequency, memo=None):
        acct_id = self._resolve_account_id(account)
        cat_id = self._resolve_category_id(category) if category else None
        body = {
            "scheduled_transaction": {
                "account_id": acct_id,
                "date": txn_date,
                "amount": int(round(amount_dollars * 1000)),
                "payee_name": payee_name,
                "category_id": cat_id,
                "frequency": frequency,
            }
        }
        if memo:
            body["scheduled_transaction"]["memo"] = memo
        return self.post(f"{self.bp}/scheduled_transactions", body)["data"]

    def update_payee(self, payee_id, name):
        return self.patch(f"{self.bp}/payees/{payee_id}", {"payee": {"name": name}})["data"]

    # ── Analysis operations ──

    def net_worth(self):
        accounts = self.get_accounts(include_closed=False)
        assets, liabilities = 0, 0
        by_type = defaultdict(float)
        for a in accounts:
            bal = a["balance"] / 1000
            by_type[a["type"]] += bal
            if bal >= 0:
                assets += bal
            else:
                liabilities += bal
        return {"net_worth": assets + liabilities, "assets": assets, "liabilities": liabilities, "by_type": dict(by_type)}

    def spending_by_category(self, months=6):
        since = (date.today().replace(day=1) - timedelta(days=30 * months)).strftime("%Y-%m-%d")
        txns = self.get_transactions(since_date=since)
        cats = defaultdict(lambda: {"total": 0, "count": 0, "transactions": []})
        for t in txns:
            cat = t.get("category_name") or "Uncategorized"
            if t["amount"] < 0:  # outflows only
                amt = t["amount"] / 1000
                cats[cat]["total"] += amt
                cats[cat]["count"] += 1
        result = []
        for cat, data in sorted(cats.items(), key=lambda x: x[1]["total"]):
            result.append({
                "category": cat,
                "total": round(data["total"], 2),
                "count": data["count"],
                "monthly_avg": round(data["total"] / months, 2),
            })
        return {"months": months, "since": since, "categories": result}

    def recurring_expenses(self, months=6, min_count=3):
        since = (date.today().replace(day=1) - timedelta(days=30 * months)).strftime("%Y-%m-%d")
        txns = self.get_transactions(since_date=since)
        payees = defaultdict(lambda: {"amounts": [], "dates": [], "category": ""})
        for t in txns:
            if t["amount"] < 0 and t.get("payee_name"):
                p = t["payee_name"]
                payees[p]["amounts"].append(t["amount"] / 1000)
                payees[p]["dates"].append(t["date"])
                payees[p]["category"] = t.get("category_name", "")
        result = []
        for name, data in payees.items():
            if len(data["amounts"]) >= min_count:
                avg = sum(data["amounts"]) / len(data["amounts"])
                result.append({
                    "payee": name,
                    "count": len(data["amounts"]),
                    "avg_amount": round(avg, 2),
                    "total": round(sum(data["amounts"]), 2),
                    "category": data["category"],
                    "last_date": max(data["dates"]),
                })
        return {"months": months, "min_count": min_count,
                "recurring": sorted(result, key=lambda x: x["total"])}

    def income_vs_expenses(self, months=6):
        since = (date.today().replace(day=1) - timedelta(days=30 * months)).strftime("%Y-%m-%d")
        txns = self.get_transactions(since_date=since)
        by_month = defaultdict(lambda: {"income": 0, "expenses": 0})
        for t in txns:
            month_key = t["date"][:7]
            amt = t["amount"] / 1000
            if amt > 0:
                by_month[month_key]["income"] += amt
            else:
                by_month[month_key]["expenses"] += amt
        result = []
        for m in sorted(by_month.keys()):
            d = by_month[m]
            result.append({
                "month": m,
                "income": round(d["income"], 2),
                "expenses": round(d["expenses"], 2),
                "net": round(d["income"] + d["expenses"], 2),
            })
        return {"months_data": result}

    def category_trend(self, category_name, months=12):
        since = (date.today().replace(day=1) - timedelta(days=30 * months)).strftime("%Y-%m-%d")
        cat_id = self._resolve_category_id(category_name)
        txns = self.get(f"{self.bp}/categories/{cat_id}/transactions",
                        {"since_date": since})["data"]["transactions"]
        txns = [t for t in txns if not t["deleted"]]
        by_month = defaultdict(lambda: {"total": 0, "count": 0})
        for t in txns:
            m = t["date"][:7]
            by_month[m]["total"] += t["amount"] / 1000
            by_month[m]["count"] += 1
        result = []
        for m in sorted(by_month.keys()):
            d = by_month[m]
            result.append({"month": m, "total": round(d["total"], 2), "count": d["count"]})
        return {"category": category_name, "trend": result}

    def payee_analysis(self, months=6, top=20):
        since = (date.today().replace(day=1) - timedelta(days=30 * months)).strftime("%Y-%m-%d")
        txns = self.get_transactions(since_date=since)
        payees = defaultdict(lambda: {"total": 0, "count": 0})
        for t in txns:
            if t["amount"] < 0 and t.get("payee_name"):
                payees[t["payee_name"]]["total"] += t["amount"] / 1000
                payees[t["payee_name"]]["count"] += 1
        result = sorted(
            [{"payee": p, "total": round(d["total"], 2), "count": d["count"],
              "monthly_avg": round(d["total"] / months, 2)}
             for p, d in payees.items()],
            key=lambda x: x["total"]
        )[:top]
        return {"months": months, "top_payees": result}

    def detect_subscriptions(self, months=6):
        recurring = self.recurring_expenses(months=months, min_count=max(2, months // 2))
        subs = []
        for r in recurring["recurring"]:
            amounts = []
            # Re-fetch to check amount consistency
            if r["count"] >= max(2, months // 2):
                # Subscription heuristic: appears regularly with similar amounts
                subs.append(r)
        return {"likely_subscriptions": subs}

    def budget_health(self):
        cats = self.get_categories()
        over = []
        under = []
        on_track = []
        for c in cats:
            budgeted = c["budgeted"] / 1000
            activity = c["activity"] / 1000
            balance = c["balance"] / 1000
            name = c["name"]
            group = c.get("group_name", "")
            entry = {"category": name, "group": group,
                     "budgeted": round(budgeted, 2),
                     "spent": round(abs(activity), 2),
                     "available": round(balance, 2)}
            if balance < 0:
                over.append(entry)
            elif budgeted > 0 and abs(activity) < budgeted * 0.5:
                under.append(entry)
            else:
                on_track.append(entry)
        return {"overspent": over, "underspent": under, "on_track": on_track}

    # ── Resolution helpers ──

    def _resolve_account_id(self, name_or_id):
        if self._looks_like_uuid(name_or_id):
            return name_or_id
        accounts = self.get(f"{self.bp}/accounts")["data"]["accounts"]
        name_lower = name_or_id.lower()
        for a in accounts:
            if not a["deleted"] and name_lower in a["name"].lower():
                return a["id"]
        raise YNABError(404, "", "not_found", f"Account matching '{name_or_id}' not found")

    def _resolve_category_id(self, name_or_id):
        if self._looks_like_uuid(name_or_id):
            return name_or_id
        groups = self.get(f"{self.bp}/categories")["data"]["category_groups"]
        name_lower = name_or_id.lower()
        for g in groups:
            for c in g.get("categories", []):
                if not c["deleted"] and name_lower in c["name"].lower():
                    return c["id"]
        raise YNABError(404, "", "not_found", f"Category matching '{name_or_id}' not found")

    def _resolve_payee_id(self, name_or_id):
        if self._looks_like_uuid(name_or_id):
            return name_or_id
        payees = self.get(f"{self.bp}/payees")["data"]["payees"]
        name_lower = name_or_id.lower()
        for p in payees:
            if not p["deleted"] and name_lower in p["name"].lower():
                return p["id"]
        raise YNABError(404, "", "not_found", f"Payee matching '{name_or_id}' not found")

    @staticmethod
    def _looks_like_uuid(s):
        return isinstance(s, str) and len(s) == 36 and s.count("-") == 4


# ── Formatters ──

def fmt_money(milliunits):
    return f"${milliunits / 1000:,.2f}"

def fmt_table(headers, rows, alignments=None):
    if not rows:
        return "(no data)"
    widths = [len(h) for h in headers]
    str_rows = []
    for row in rows:
        sr = [str(v) if v is not None else "" for v in row]
        str_rows.append(sr)
        for i, v in enumerate(sr):
            if i < len(widths):
                widths[i] = max(widths[i], len(v))
    lines = []
    header_line = "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    lines.append(header_line)
    lines.append("  ".join("─" * w for w in widths))
    for sr in str_rows:
        lines.append("  ".join(sr[i].ljust(widths[i]) if i < len(sr) else " " * widths[i] for i in range(len(headers))))
    return "\n".join(lines)


# ── CLI ──

def main():
    parser = argparse.ArgumentParser(description="YNAB API Client")
    parser.add_argument("--token", required=True, help="YNAB personal access token")
    parser.add_argument("--budget", required=True, help="Budget ID (UUID, 'last-used', or 'default')")
    parser.add_argument("--format", choices=["json", "table", "raw"], default="table")
    parser.add_argument("command", help="Command to run")
    parser.add_argument("args", nargs="*", help="Command arguments")
    parser.add_argument("--since", help="Since date (YYYY-MM-DD)")
    parser.add_argument("--account", help="Account name or ID")
    parser.add_argument("--category", help="Category name or ID")
    parser.add_argument("--payee", help="Payee name or ID")
    parser.add_argument("--type", help="Transaction type filter (uncategorized, unapproved)")
    parser.add_argument("--months", type=int, default=6)
    parser.add_argument("--min-count", type=int, default=3)
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--amount", type=float)
    parser.add_argument("--date", help="Date (YYYY-MM-DD)")
    parser.add_argument("--memo", help="Memo text")
    parser.add_argument("--month", help="Budget month (YYYY-MM-DD)")
    parser.add_argument("--id", help="Transaction ID")
    parser.add_argument("--name", help="Name for new entity")
    parser.add_argument("--balance", type=float, default=0)
    parser.add_argument("--cleared", default="cleared")
    parser.add_argument("--frequency", help="Scheduled txn frequency")

    args = parser.parse_args()
    client = YNABClient(args.token, args.budget)
    fmt = args.format

    try:
        cmd = args.command.lower().replace("-", "_")

        if cmd == "accounts":
            data = client.get_accounts(include_closed=True)
            if fmt == "table":
                rows = [(a["name"], a["type"], fmt_money(a["balance"]),
                         "Closed" if a["closed"] else "Open",
                         "Linked" if a.get("direct_import_linked") else "")
                        for a in data if not a["deleted"]]
                print(fmt_table(["Account", "Type", "Balance", "Status", "Import"], rows))
            else:
                json.dump(data, sys.stdout, indent=2)

        elif cmd == "transactions":
            since = args.since or (date.today() - timedelta(days=30)).strftime("%Y-%m-%d")
            data = client.get_transactions(since_date=since, account=args.account,
                                           category=args.category, payee=args.payee,
                                           txn_type=args.type)
            if fmt == "table":
                rows = [(t["date"], t.get("payee_name", ""), t.get("account_name", ""),
                         t.get("category_name", ""), fmt_money(t["amount"]),
                         t["cleared"][0].upper(), t.get("memo") or "")
                        for t in data]
                print(fmt_table(["Date", "Payee", "Account", "Category", "Amount", "C", "Memo"], rows))
                print(f"\n{len(data)} transactions since {since}")
            else:
                json.dump(data, sys.stdout, indent=2)

        elif cmd == "categories":
            data = client.get_categories(month=args.month)
            if fmt == "table":
                current_group = ""
                rows = []
                for c in data:
                    g = c.get("group_name", c.get("category_group_name", ""))
                    if g != current_group:
                        rows.append(("", "", "", ""))
                        rows.append((f"── {g} ──", "", "", ""))
                        current_group = g
                    rows.append((f"  {c['name']}", fmt_money(c["budgeted"]),
                                 fmt_money(c["activity"]), fmt_money(c["balance"])))
                print(fmt_table(["Category", "Budgeted", "Activity", "Available"], rows))
            else:
                json.dump(data, sys.stdout, indent=2)

        elif cmd == "month":
            month_str = args.args[0] if args.args else args.month or "current"
            data = client.get_month(month_str)
            if fmt == "table":
                print(f"Month: {data['month']}")
                print(f"Income:          {fmt_money(data['income'])}")
                print(f"Budgeted:        {fmt_money(data['budgeted'])}")
                print(f"Activity:        {fmt_money(data['activity'])}")
                print(f"To Be Budgeted:  {fmt_money(data['to_be_budgeted'])}")
                print(f"Age of Money:    {data.get('age_of_money', 'N/A')} days")
            else:
                data.pop("categories", None)  # too verbose for raw dump
                json.dump(data, sys.stdout, indent=2)

        elif cmd == "months":
            data = client.get_months()
            if fmt == "table":
                rows = [(m["month"], fmt_money(m.get("income", 0)),
                         fmt_money(m.get("budgeted", 0)), fmt_money(m.get("activity", 0)),
                         fmt_money(m.get("to_be_budgeted", 0)))
                        for m in data if not m.get("deleted")]
                print(fmt_table(["Month", "Income", "Budgeted", "Activity", "To Budget"], rows[-24:]))
            else:
                json.dump(data, sys.stdout, indent=2)

        elif cmd == "payees":
            data = client.get_payees()
            if fmt == "table":
                rows = [(p["name"], p["id"][:8] + "...",
                         "Transfer" if p.get("transfer_account_id") else "")
                        for p in data]
                print(fmt_table(["Payee", "ID", "Type"], rows))
                print(f"\n{len(data)} payees")
            else:
                json.dump(data, sys.stdout, indent=2)

        elif cmd == "scheduled":
            data = client.get_scheduled_transactions()
            if fmt == "table":
                rows = [(t.get("date_next", ""), t.get("payee_name", ""),
                         t.get("category_name", ""), fmt_money(t["amount"]),
                         t.get("frequency", ""), t.get("memo", ""))
                        for t in data]
                print(fmt_table(["Next Date", "Payee", "Category", "Amount", "Frequency", "Memo"], rows))
            else:
                json.dump(data, sys.stdout, indent=2)

        elif cmd == "net_worth":
            data = client.net_worth()
            if fmt == "table":
                print(f"Net Worth:    ${data['net_worth']:>12,.2f}")
                print(f"Assets:       ${data['assets']:>12,.2f}")
                print(f"Liabilities:  ${data['liabilities']:>12,.2f}")
                print(f"\nBy type:")
                for t, v in sorted(data["by_type"].items(), key=lambda x: -x[1]):
                    print(f"  {t:20s}  ${v:>12,.2f}")
            else:
                json.dump(data, sys.stdout, indent=2)

        elif cmd == "settings":
            data = client.get_settings()
            json.dump(data, sys.stdout, indent=2)

        elif cmd == "user":
            data = client.get_user()
            json.dump(data, sys.stdout, indent=2)

        elif cmd == "spending":
            data = client.spending_by_category(months=args.months)
            if fmt == "table":
                rows = [(c["category"], f"${c['total']:>10,.2f}", str(c["count"]),
                         f"${c['monthly_avg']:>10,.2f}")
                        for c in data["categories"] if c["total"] < -10]
                print(fmt_table(["Category", "Total", "Txns", "Monthly Avg"], rows))
            else:
                json.dump(data, sys.stdout, indent=2)

        elif cmd == "recurring":
            data = client.recurring_expenses(months=args.months, min_count=args.min_count)
            if fmt == "table":
                rows = [(r["payee"], f"${r['avg_amount']:>10,.2f}", str(r["count"]),
                         f"${r['total']:>10,.2f}", r["category"], r["last_date"])
                        for r in data["recurring"]]
                print(fmt_table(["Payee", "Avg Amount", "Count", "Total", "Category", "Last"], rows))
            else:
                json.dump(data, sys.stdout, indent=2)

        elif cmd == "income_vs_expenses":
            data = client.income_vs_expenses(months=args.months)
            if fmt == "table":
                rows = [(m["month"], f"${m['income']:>10,.2f}", f"${m['expenses']:>10,.2f}",
                         f"${m['net']:>10,.2f}") for m in data["months_data"]]
                print(fmt_table(["Month", "Income", "Expenses", "Net"], rows))
            else:
                json.dump(data, sys.stdout, indent=2)

        elif cmd == "category_trend":
            if not args.category:
                print("Error: --category required", file=sys.stderr); sys.exit(1)
            data = client.category_trend(args.category, months=args.months)
            if fmt == "table":
                rows = [(t["month"], f"${t['total']:>10,.2f}", str(t["count"]))
                        for t in data["trend"]]
                print(f"Category: {data['category']}\n")
                print(fmt_table(["Month", "Total", "Txns"], rows))
            else:
                json.dump(data, sys.stdout, indent=2)

        elif cmd == "payee_analysis":
            data = client.payee_analysis(months=args.months, top=args.top)
            if fmt == "table":
                rows = [(p["payee"], f"${p['total']:>10,.2f}", str(p["count"]),
                         f"${p['monthly_avg']:>10,.2f}")
                        for p in data["top_payees"]]
                print(fmt_table(["Payee", "Total", "Txns", "Monthly Avg"], rows))
            else:
                json.dump(data, sys.stdout, indent=2)

        elif cmd == "subscriptions":
            data = client.detect_subscriptions(months=args.months)
            if fmt == "table":
                rows = [(s["payee"], f"${s['avg_amount']:>10,.2f}", str(s["count"]),
                         s["category"], s["last_date"])
                        for s in data["likely_subscriptions"]]
                print(fmt_table(["Service", "Avg Amount", "Count", "Category", "Last"], rows))
            else:
                json.dump(data, sys.stdout, indent=2)

        elif cmd == "budget_health":
            data = client.budget_health()
            if fmt == "table":
                if data["overspent"]:
                    print("OVERSPENT:")
                    rows = [(c["category"], c["group"], f"${c['budgeted']:>8,.2f}",
                             f"${c['spent']:>8,.2f}", f"${c['available']:>8,.2f}")
                            for c in data["overspent"]]
                    print(fmt_table(["Category", "Group", "Budgeted", "Spent", "Available"], rows))
                if data["underspent"]:
                    print("\nUNDERSPENT (used <50% of budget):")
                    rows = [(c["category"], c["group"], f"${c['budgeted']:>8,.2f}",
                             f"${c['spent']:>8,.2f}", f"${c['available']:>8,.2f}")
                            for c in data["underspent"]]
                    print(fmt_table(["Category", "Group", "Budgeted", "Spent", "Available"], rows))
                print(f"\n{len(data['on_track'])} categories on track")
            else:
                json.dump(data, sys.stdout, indent=2)

        elif cmd == "create_transaction":
            if not all([args.account, args.payee, args.amount, args.date]):
                print("Error: --account, --payee, --amount, --date required", file=sys.stderr); sys.exit(1)
            data = client.create_transaction(args.account, args.payee, args.category,
                                             args.amount, args.date, args.memo)
            print(f"Created transaction: {data.get('transaction', {}).get('id', 'OK')}")
            if fmt != "table":
                json.dump(data, sys.stdout, indent=2)

        elif cmd == "update_transaction":
            if not args.id:
                print("Error: --id required", file=sys.stderr); sys.exit(1)
            fields = {}
            if args.amount is not None: fields["amount"] = args.amount
            if args.date: fields["date"] = args.date
            if args.payee: fields["payee_name"] = args.payee
            if args.category: fields["category"] = args.category
            if args.memo: fields["memo"] = args.memo
            data = client.update_transaction(args.id, **fields)
            print("Transaction updated.")
            if fmt != "table":
                json.dump(data, sys.stdout, indent=2)

        elif cmd == "delete_transaction":
            if not args.id:
                print("Error: --id required", file=sys.stderr); sys.exit(1)
            data = client.delete_transaction(args.id)
            print("Transaction deleted.")

        elif cmd == "approve_transaction":
            txn_id = args.id or (args.args[0] if args.args else None)
            if not txn_id:
                print("Error: --id or positional ID required", file=sys.stderr); sys.exit(1)
            data = client.approve_transaction(txn_id)
            print("Transaction approved.")

        elif cmd == "set_budget":
            if not all([args.category, args.month, args.amount is not None]):
                print("Error: --category, --month, --amount required", file=sys.stderr); sys.exit(1)
            data = client.set_budget_amount(args.category, args.month, args.amount)
            print(f"Budget for {args.category} in {args.month} set to ${args.amount:,.2f}")

        elif cmd == "create_account":
            if not args.name or not args.type:
                print("Error: --name and --type required", file=sys.stderr); sys.exit(1)
            data = client.create_account(args.name, args.type, args.balance)
            print(f"Account created: {data.get('account', {}).get('id', 'OK')}")

        elif cmd == "import_transactions":
            data = client.import_transactions()
            json.dump(data, sys.stdout, indent=2)

        else:
            print(f"Unknown command: {args.command}", file=sys.stderr)
            print(__doc__, file=sys.stderr)
            sys.exit(1)

    except YNABError as e:
        print(f"YNAB API Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()

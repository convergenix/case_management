# Time Tracking Reports Overhaul — Design

**Date:** 2026-05-25
**Status:** Approved for implementation
**Scope:** Sub-project A of the broader "Toggl-compatible time tracking" initiative. Sub-projects B (Toggl-style weekly/calendar views) and C (one-click invoicing flow) are out of scope and will get their own specs.

## Motivation

The app already has two Frappe Query Reports — **Time Management Report** (detailed entries) and **Time Management Summary Report** (per-employee aggregates) — but they're missing the filter dimensions and duration formatting that users get from Toggl Track's Detailed and Summary reports. Users have to mentally convert decimal hours and can only filter by `user / client / date`, which forces them to scroll through irrelevant rows when investigating a single matter or a single employee's billable load.

This spec covers the minimum changes needed to bring both reports up to filter/column parity with the Toggl reports the team currently uses externally. No custom PDF print format, no charts, no UI summary cards — those are explicitly deferred.

## Non-Goals

- Custom PDF print format with firm logo (out — explicitly declined).
- Summary cards (Total Hours / Billable / Amount / Avg Daily Hours) rendered above the table in the UI (out).
- Bar chart "Duration by week" and donut "Project distribution" (out).
- Tag filter and new Tag doctype on Time Tracking (deferred — no data model change in v1).
- Rounding toggle (deferred).
- Toggl-style weekly grid / calendar / list views of Time Tracking entries (Sub-project B).
- Generate-invoice-from-billable-entries workflow (Sub-project C).

## Files Touched

```
case_management/case_management/report/
├── time_management_report/
│   ├── time_management_report.py
│   └── time_management_report.js
└── time_management_summary_report/
    ├── time_management_summary_report.py
    └── time_management_summary_report.js
```

No new doctypes, no new fields on existing doctypes, no migrations.

## Filter Signature (Both Reports)

| Filter | Type | Status | Notes |
|---|---|---|---|
| `from_date` | Date | existing | unchanged |
| `to_date` | Date | existing | unchanged |
| `matter` | Link → Matter | **new** | filters `tt.matter` directly |
| `client` | Link → Customer | existing on Detailed; **new on Summary** | dual-match `tt.matter_name = %(client)s OR m.client = %(client)s` (preserves existing defensive logic) |
| `employee` | Link → Employee | **new** | visible filter; filters `tt.employee` directly when set, else falls back to user→employee resolution |
| `billing` | Select | **new** | options: `""` (All) / `Billable` / `Non-Billable` |
| `user` | Link → User | existing | kept for backward compat but de-emphasized in the .js (no default, no `reqd`); legacy callers continue to work |

## Column Changes — Detailed Report

`time_management_report.py` — `get_columns()` becomes:

| Label | Fieldname | Fieldtype | Width | Status |
|---|---|---|---|---|
| Description | notes | Data | 300 | existing |
| Duration | time | Float | 100 | existing (formatter added in JS) |
| Member | creator_name | Data | 200 | existing |
| Start Date | creation | Date | 180 | existing |
| Matter | matter | Link → Matter | 200 | existing |
| Client | client_name | Data | 200 | existing |
| Billing | billing | Data | 100 | **new** |
| Amount (₦) | revenue_in_naira | Currency | 120 | **new** |

`get_data()` SELECT clause adds `tt.billing` and `tt.revenue_in_naira`. Amount is always in NGN since `calculate_revenue()` already normalizes there.

## Column Changes — Summary Report

No column changes. Existing columns (Employee / Total Hours / Billable Hours / Billable % / Amount / Avg Daily Hours) are kept. Duration columns gain the JS formatter; new filters get added to the .js and translated into SQL conditions in `get_data()`.

## Duration Formatter (JS)

Identical helper in both `.js` files. Defined once at top of file, referenced from each column's `formatter` callback.

```js
const fmtHHMMSS = (hours) => {
    if (!hours) return "";
    const total = Math.round(hours * 3600);
    const h = String(Math.floor(total / 3600)).padStart(2, "0");
    const m = String(Math.floor((total % 3600) / 60)).padStart(2, "0");
    const s = String(total % 60).padStart(2, "0");
    return `${h}:${m}:${s}`;
};
```

Wired per-column:

```js
formatter: (value, row, column, data, default_formatter) => fmtHHMMSS(value)
```

Columns formatted:
- **Detailed report:** `time` column.
- **Summary report:** `total_hours` and `billable_hours` columns.

The underlying Float values are unchanged, so sorting and Excel export still see numeric hours. Display only.

Empty/zero values render as `""` rather than `"00:00:00"` — keeps incomplete rows visually quiet.

## SQL Condition Builder

To keep `get_data()` readable as filters grow, extract:

```python
def _build_conditions(filters):
    conditions = ["tt.docstatus = 1"]
    values = {}

    if filters.get("from_date"):
        conditions.append("DATE(tt.start_time) >= %(from_date)s")
        values["from_date"] = filters["from_date"]
    if filters.get("to_date"):
        conditions.append("DATE(tt.end_time) <= %(to_date)s")
        values["to_date"] = filters["to_date"]
    if filters.get("matter"):
        conditions.append("tt.matter = %(matter)s")
        values["matter"] = filters["matter"]
    if filters.get("client"):
        conditions.append("(tt.matter_name = %(client)s OR m.client = %(client)s)")
        values["client"] = filters["client"]
    if filters.get("employee"):
        conditions.append("tt.employee = %(employee)s")
        values["employee"] = filters["employee"]
    if filters.get("billing"):
        conditions.append("tt.billing = %(billing)s")
        values["billing"] = filters["billing"]
    if filters.get("user") and not filters.get("employee"):
        emp = frappe.db.get_value("Employee", {"user_id": filters["user"]}, "name")
        if emp:
            conditions.append("tt.employee = %(employee_from_user)s")
            values["employee_from_user"] = emp
        else:
            conditions.append("tt.owner = %(user)s")
            values["user"] = filters["user"]

    return " AND ".join(conditions), values
```

Both reports import this helper. The Summary report's existing employee-from-user resolution moves into the helper unchanged.

The `LEFT JOIN tabMatter m` stays in both queries (cheap, already there, needed for the client OR-condition).

## Edge Cases

- **Mixed billing currencies.** `revenue_in_naira` is normalized to NGN by `TimeTracking.calculate_revenue()` regardless of source currency. The Amount column header reads "Amount (₦)" to make the unit explicit. Rows where revenue is `NULL` or `0` show empty.
- **Entries with `time = NULL` or `0`.** Formatter returns `""` rather than `"00:00:00"`. Keeps mid-tracking entries visually quiet.
- **Employee filter set but `tt.employee` is `NULL`.** Filter is exclusive — entries without `tt.employee` set are excluded. Acceptable: `tt.employee` is `reqd: 1` in the doctype JSON, so this only affects very old rows.
- **`user` filter still passed by legacy callers.** Resolved to Employee via `Employee.user_id`; if no Employee mapping exists, falls back to `tt.owner` (preserves existing Summary report behavior).
- **`employee` and `user` both passed.** `employee` wins (more specific). Helper short-circuits the `user` branch when `employee` is set.

## Backward Compatibility

- Existing API: `execute(filters)` signature unchanged.
- Existing filters (`user`, `client`, `from_date`, `to_date`) keep working with identical semantics.
- Existing columns (label/fieldname/order on rows already present) are unchanged. Excel exports of the Detailed report gain two new trailing columns (Billing, Amount); no consumer reorders are required.
- No DB migration. No fixtures. No hooks change.

## Testing

Behavioral tests per the project's testing rule (real bench DB, no implementation mocks):

**Test 1 — Filter correctness.** In `test_time_management_report.py`:
1. Seed 3 Time Tracking entries:
   - Entry A: Matter M1, Employee E1, Billable, 2.5h
   - Entry B: Matter M1, Employee E2, Non-Billable, 1.0h
   - Entry C: Matter M2, Employee E1, Billable, 0.75h
2. For each new filter, call `execute({...})` with just that filter set, assert the row count and the row names match.
3. Call `execute({})` (no filters), assert all 3 returned.

**Test 2 — Cross-report consistency.** Same seed. Call Detailed `execute()` filtered to Employee E1; sum `revenue_in_naira` across returned rows. Call Summary `execute()` filtered to Employee E1; read `amount` from the single returned row. Assert the two totals match.

**Test 3 — Duration formatter.** Pure JS function; verified manually in the browser report view. Confirm `2.5` → `"02:30:00"`, `0` → `""`, `null` → `""`, `1.0833` → `"01:05:00"`.

## Risk

Low. Read-only reports, no mutation, no doctype changes. The biggest behavior change visible to existing users is the duration display flipping from decimal hours to `HH:MM:SS` — this is intentional and matches the external reports the team already uses.

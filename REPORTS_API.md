# Reports API Endpoints

This document describes the API endpoints available for the Reports & Analytics section.

## Base URL
`/api/reports`

## Endpoints

### 1. Get Dashboard Statistics
**GET** `/api/reports/stats`

Returns key statistics for the reports dashboard including:
- Today's statistics (revenue, profit, orders, customers)
- This week's statistics
- This month's statistics
- Total statistics (all time)

### 2. Get Sales Data
**GET** `/api/reports/sales-data`

Returns detailed sales data for a specific date range.

**Query Parameters:**
- `from_date` (optional): Start date (YYYY-MM-DD)
- `to_date` (optional): End date (YYYY-MM-DD)

### 3. Get Sales Trends
**GET** `/api/reports/sales-trends`

Returns sales trends for the last N days (default 30 days).

**Query Parameters:**
- `days` (optional): Number of days to show trends for (default: 30)

### 4. Get Sales Reports
**GET** `/api/reports/sales-reports`

Returns detailed sales reports with filtering options.

**Query Parameters:**
- `from_date` (optional): Start date (YYYY-MM-DD)
- `to_date` (optional): End date (YYYY-MM-DD)

### 5. Get Inventory Reports
**GET** `/api/reports/inventory-reports`

Returns inventory reports including:
- Low stock products
- Inventory valuation
- Category-wise inventory

### 6. Get Customer Reports
**GET** `/api/reports/customer-reports`

Returns customer analytics and reports including:
- Top customers by purchase value
- Customer statistics
- Customer purchase trends

### 7. Get Financial Reports
**GET** `/api/reports/financial-reports`

Returns financial reports including:
- Profit and loss analysis
- Expense breakdown
- Net profit calculation

**Query Parameters:**
- `from_date` (optional): Start date (YYYY-MM-DD)
- `to_date` (optional): End date (YYYY-MM-DD)

### 8. Export All Data
**GET** `/api/reports/export-data`

Exports all data for reporting purposes including:
- Sales data
- Products data
- Customers data
- Expenses data

## Response Format

All endpoints return JSON responses in the following format:

```json
{
  "success": true,
  "data": {
    // Endpoint-specific data
  }
}
```

Or in case of an error:

```json
{
  "success": false,
  "error": "Error message"
}
```
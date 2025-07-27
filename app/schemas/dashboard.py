from pydantic import BaseModel, Field
from typing import List, Dict, Any
from datetime import datetime
from enum import Enum


class ReportPeriod(str, Enum):
    TODAY = "today"
    YESTERDAY = "yesterday"
    THIS_WEEK = "this_week"
    LAST_WEEK = "last_week"
    THIS_MONTH = "this_month"
    LAST_MONTH = "last_month"
    CUSTOM = "custom"


class SalesOverview(BaseModel):
    total_sales: float
    total_transactions: int
    average_transaction_value: float
    total_items_sold: int

    class Config:
        schema_extra = {
            "example": {
                "total_sales": 58277850,
                "total_transactions": 125,
                "average_transaction_value": 466223,
                "total_items_sold": 350
            }
        }


class InventoryOverview(BaseModel):
    total_products: int
    active_products: int
    low_stock_products: int
    out_of_stock_products: int
    total_inventory_value: float

    class Config:
        schema_extra = {
            "example": {
                "total_products": 500,
                "active_products": 485,
                "low_stock_products": 25,
                "out_of_stock_products": 5,
                "total_inventory_value": 125000.00
            }
        }


class TopSellingProduct(BaseModel):
    product_id: str
    product_name: str
    sku: str
    quantity_sold: int
    total_revenue: float

    class Config:
        schema_extra = {
            "example": {
                "product_id": "507f1f77bcf86cd799439011",
                "product_name": "iPhone 15 Pro",
                "sku": "IPH15PRO001",
                "quantity_sold": 25,
                "total_revenue": 24999.75
            }
        }


class LowStockProduct(BaseModel):
    product_id: str
    product_name: str
    sku: str
    current_stock: int
    min_stock_level: int
    stock_difference: int

    class Config:
        schema_extra = {
            "example": {
                "product_id": "507f1f77bcf86cd799439011",
                "product_name": "iPhone 15 Pro",
                "sku": "IPH15PRO001",
                "current_stock": 5,
                "min_stock_level": 10,
                "stock_difference": -5
            }
        }


class SalesReport(BaseModel):
    period: str
    start_date: datetime
    end_date: datetime
    sales_overview: SalesOverview
    top_selling_products: List[TopSellingProduct]
    sales_by_payment_method: Dict[str, float]
    daily_sales: List[Dict[str, Any]]  # Date and sales amount

    class Config:
        schema_extra = {
            "example": {
                "period": "this_month",
                "start_date": "2024-01-01T00:00:00Z",
                "end_date": "2024-01-31T23:59:59Z",
                "sales_overview": {
                    "total_sales": 15750.50,
                    "total_transactions": 125,
                    "average_transaction_value": 126.00,
                    "total_items_sold": 350
                },
                "top_selling_products": [
                    {
                        "product_name": "iPhone 15 Pro",
                        "quantity_sold": 25,
                        "total_revenue": 24999.75
                    }
                ],
                "sales_by_payment_method": {
                    "card": 12000.50,
                    "cash": 3750.00
                },
                "daily_sales": [
                    {"date": "2024-01-01", "sales": 1250.00},
                    {"date": "2024-01-02", "sales": 1500.00}
                ]
            }
        }


class InventoryReport(BaseModel):
    inventory_overview: InventoryOverview
    low_stock_products: List[LowStockProduct]
    categories_summary: List[Dict[str, Any]]

    class Config:
        schema_extra = {
            "example": {
                "inventory_overview": {
                    "total_products": 500,
                    "active_products": 485,
                    "low_stock_products": 25,
                    "out_of_stock_products": 5,
                    "total_inventory_value": 125000.00
                },
                "low_stock_products": [
                    {
                        "product_name": "iPhone 15 Pro",
                        "current_stock": 5,
                        "min_stock_level": 10,
                        "stock_difference": -5
                    }
                ],
                "categories_summary": [
                    {"category": "Electronics", "product_count": 150, "total_value": 75000.00}
                ]
            }
        }


class DashboardSummary(BaseModel):
    sales_overview: SalesOverview
    inventory_overview: InventoryOverview
    recent_sales_count: int
    low_stock_alerts: int
    top_selling_products: List[TopSellingProduct]

    class Config:
        schema_extra = {
            "example": {
                "sales_overview": {
                    "total_sales": 15750.50,
                    "total_transactions": 125,
                    "average_transaction_value": 126.00,
                    "total_items_sold": 350
                },
                "inventory_overview": {
                    "total_products": 500,
                    "active_products": 485,
                    "low_stock_products": 25,
                    "out_of_stock_products": 5,
                    "total_inventory_value": 125000.00
                },
                "recent_sales_count": 15,
                "low_stock_alerts": 25,
                "top_selling_products": [
                    {
                        "product_name": "iPhone 15 Pro",
                        "quantity_sold": 25,
                        "total_revenue": 24999.75
                    }
                ]
            }
        }
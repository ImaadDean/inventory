# Inventory Management System with POS

A comprehensive inventory management system with Point of Sale functionality built with FastAPI and MongoDB.

## Features

### 👤 Authentication
- JWT-based authentication
- Role-based access control (Admin, Cashier, Inventory Manager)
- User registration and login
- Password change functionality

### 📦 Inventory Management
- Product and category management
- Stock level tracking with low stock alerts
- Barcode and SKU support
- Supplier information tracking
- Automatic stock updates after sales

### 🧾 Point of Sale (POS) System
- Create sales transactions
- Product search by name, SKU, or barcode
- Multiple payment methods support
- Automatic stock deduction
- Receipt generation data
- Customer association with sales

### 📊 Dashboard & Reports
- Sales overview and analytics
- Inventory status summary
- Top-selling products
- Low stock alerts
- Daily, weekly, monthly reports

### 👥 Customer Management
- Customer database with contact information
- Purchase history tracking
- Customer statistics (total purchases, orders)

## Technology Stack

- **Backend**: Python 3.x, FastAPI
- **Database**: MongoDB with Motor (async driver)
- **Authentication**: JWT with python-jose
- **Password Hashing**: bcrypt via passlib
- **Validation**: Pydantic v2
- **Documentation**: Automatic OpenAPI/Swagger docs

## Project Structure

```
inventory/
├── app/
│   ├── config/
│   │   ├── __init__.py
│   │   ├── settings.py          # Application settings
│   │   └── database.py          # MongoDB connection
│   ├── models/
│   │   ├── __init__.py
│   │   ├── user.py              # User model
│   │   ├── product.py           # Product and Category models
│   │   ├── customer.py          # Customer model
│   │   └── sale.py              # Sale and SaleItem models
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── auth.py              # Authentication schemas
│   │   ├── user.py              # User management schemas
│   │   ├── product.py           # Product schemas
│   │   ├── customer.py          # Customer schemas
│   │   ├── pos.py               # POS schemas
│   │   └── dashboard.py         # Dashboard schemas
│   ├── routes/                  # Modular route structure
│   │   ├── __init__.py
│   │   ├── auth/
│   │   │   ├── __init__.py
│   │   │   ├── api.py           # Authentication API routes
│   │   │   └── route.py         # Authentication HTML routes
│   │   ├── users/
│   │   │   ├── __init__.py
│   │   │   ├── api.py           # User management API routes
│   │   │   └── route.py         # User management HTML routes
│   │   ├── products/
│   │   │   ├── __init__.py
│   │   │   ├── api.py           # Product management API routes
│   │   │   └── route.py         # Product management HTML routes
│   │   ├── customers/
│   │   │   ├── __init__.py
│   │   │   ├── api.py           # Customer management API routes
│   │   │   └── route.py         # Customer management HTML routes
│   │   ├── pos/
│   │   │   ├── __init__.py
│   │   │   ├── api.py           # POS API routes
│   │   │   └── route.py         # POS HTML routes
│   │   └── dashboard/
│   │       ├── __init__.py
│   │       ├── api.py           # Dashboard API routes
│   │       └── route.py         # Dashboard HTML routes
│   ├── templates/               # Jinja2 HTML templates with Tailwind CSS
│   │   ├── base.html            # Base template with navigation
│   │   ├── auth/
│   │   │   ├── login.html       # Login page
│   │   │   └── register.html    # Registration page
│   │   ├── dashboard/
│   │   │   └── index.html       # Dashboard page
│   │   ├── pos/
│   │   │   └── index.html       # POS interface
│   │   ├── products/            # Product management templates
│   │   ├── customers/           # Customer management templates
│   │   ├── users/               # User management templates
│   │   └── components/          # Reusable template components
│   └── utils/
│       ├── __init__.py
│       └── auth.py              # Authentication utilities
├── main.py                      # FastAPI application
├── start.py                     # Convenient startup script
├── requirements.txt             # Python dependencies
└── README.md                    # This file
```

## Installation

1. **Clone the repository**
```bash
git clone <repository-url>
cd inventory
```

2. **Create virtual environment**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Environment Configuration**
Create a `.env` file in the root directory:
```env
MONGODB_USERNAME=imaad
MONGODB_PASSWORD=Ertdfgxc
MONGODB_HOST=144.21.56.184
MONGODB_PORT=27017
MONGODB_DATABASE=inventory
SECRET_KEY=your-secret-key-change-this-in-production
DEBUG=True
```

5. **Run the application**
```bash
python main.py
```

The application will be available at:
- **Web Interface**: http://localhost:8000 (redirects to login)
- **API**: http://localhost:8000/api
- **Interactive Docs**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## Web Interface

The system now includes a modern web interface built with Tailwind CSS:

### Authentication Pages
- **Login**: http://localhost:8000/auth/login
- **Register**: http://localhost:8000/auth/register

### Main Application Pages
- **Dashboard**: http://localhost:8000/dashboard
- **Point of Sale**: http://localhost:8000/pos
- **Products**: http://localhost:8000/products
- **Customers**: http://localhost:8000/customers
- **Users**: http://localhost:8000/users (Admin only)

## API Documentation

### Authentication (API)

#### Register User
```http
POST /api/auth/register
Content-Type: application/json

{
  "username": "john_doe",
  "email": "john@example.com",
  "full_name": "John Doe",
  "password": "securepassword123",
  "role": "cashier"
}
```

#### Login
```http
POST /api/auth/login
Content-Type: application/json

{
  "username": "john_doe",
  "password": "securepassword123"
}
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 1800,
  "user": {
    "id": "507f1f77bcf86cd799439011",
    "username": "john_doe",
    "email": "john@example.com",
    "full_name": "John Doe",
    "role": "cashier",
    "is_active": true
  }
}
```

### Product Management (API)

#### Create Product
```http
POST /api/products/
Authorization: Bearer <token>
Content-Type: application/json

{
  "name": "iPhone 15 Pro",
  "description": "Latest iPhone model with advanced features",
  "sku": "IPH15PRO001",
  "barcode": "1234567890123",
  "category_id": "507f1f77bcf86cd799439010",
  "price": 999.99,
  "cost_price": 750.00,
  "stock_quantity": 50,
  "min_stock_level": 10,
  "unit": "pcs",
  "supplier": "Apple Inc."
}
```

#### Get Products
```http
GET /api/products/?page=1&size=10&search=iPhone&low_stock_only=false
Authorization: Bearer <token>
```

### Customer Management (API)

#### Create Customer
```http
POST /api/customers/
Authorization: Bearer <token>
Content-Type: application/json

{
  "name": "Jane Smith",
  "email": "jane@example.com",
  "phone": "+1234567890",
  "address": "123 Main St",
  "city": "New York",
  "postal_code": "10001",
  "country": "USA"
}
```

### Point of Sale (API)

#### Search Products for POS
```http
GET /api/pos/products/search?query=iPhone&limit=10
Authorization: Bearer <token>
```

#### Create Sale
```http
POST /api/pos/sales
Authorization: Bearer <token>
Content-Type: application/json

{
  "customer_name": "John Doe",
  "items": [
    {
      "product_id": "507f1f77bcf86cd799439011",
      "quantity": 1,
      "discount_amount": 0.0
    }
  ],
  "tax_rate": 0.08,
  "discount_amount": 50.0,
  "payment_method": "card",
  "payment_received": 1000.0,
  "notes": "Customer paid with credit card"
}
```

### Dashboard (API)

#### Get Dashboard Summary
```http
GET /api/dashboard/summary
Authorization: Bearer <token>
```

**Response:**
```json
{
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
      "product_id": "507f1f77bcf86cd799439011",
      "product_name": "iPhone 15 Pro",
      "sku": "IPH15PRO001",
      "quantity_sold": 25,
      "total_revenue": 24999.75
    }
  ]
}
```

## User Roles and Permissions

### Admin
- Full system access
- User management (create, update, delete users)
- All inventory management functions
- All POS functions
- All dashboard and reports

### Inventory Manager
- Product and category management
- Stock level management
- Inventory reports
- Customer management
- Basic dashboard access

### Cashier
- POS operations (create sales)
- Product search
- Customer lookup
- Basic sales reports

## Database Schema

### Users Collection
```javascript
{
  "_id": ObjectId,
  "username": String,
  "email": String,
  "full_name": String,
  "hashed_password": String,
  "role": String, // "admin", "cashier", "inventory_manager"
  "is_active": Boolean,
  "created_at": Date,
  "updated_at": Date,
  "last_login": Date
}
```

### Products Collection
```javascript
{
  "_id": ObjectId,
  "name": String,
  "description": String,
  "sku": String,
  "barcode": String,
  "category_id": ObjectId,
  "price": Number,
  "cost_price": Number,
  "stock_quantity": Number,
  "min_stock_level": Number,
  "max_stock_level": Number,
  "unit": String,
  "supplier": String,
  "is_active": Boolean,
  "created_at": Date,
  "updated_at": Date
}
```

### Sales Collection
```javascript
{
  "_id": ObjectId,
  "sale_number": String,
  "customer_id": ObjectId,
  "customer_name": String,
  "cashier_id": ObjectId,
  "cashier_name": String,
  "items": [
    {
      "product_id": ObjectId,
      "product_name": String,
      "sku": String,
      "quantity": Number,
      "unit_price": Number,
      "total_price": Number,
      "discount_amount": Number
    }
  ],
  "subtotal": Number,
  "tax_amount": Number,
  "discount_amount": Number,
  "total_amount": Number,
  "payment_method": String,
  "payment_received": Number,
  "change_given": Number,
  "status": String,
  "notes": String,
  "created_at": Date,
  "updated_at": Date
}
```

## Testing the API

### Using curl

1. **Register a user:**
```bash
curl -X POST "http://localhost:8000/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "email": "admin@example.com",
    "full_name": "System Admin",
    "password": "admin123",
    "role": "admin"
  }'
```

2. **Login:**
```bash
curl -X POST "http://localhost:8000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "password": "admin123"
  }'
```

3. **Create a product (using token from login):**
```bash
curl -X POST "http://localhost:8000/products/" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Product",
    "sku": "TEST001",
    "price": 29.99,
    "stock_quantity": 100,
    "min_stock_level": 10
  }'
```

### Using Python requests

```python
import requests

# Base URL
BASE_URL = "http://localhost:8000"

# Login
login_response = requests.post(f"{BASE_URL}/auth/login", json={
    "username": "admin",
    "password": "admin123"
})
token = login_response.json()["access_token"]

# Headers with authentication
headers = {"Authorization": f"Bearer {token}"}

# Create a product
product_data = {
    "name": "Sample Product",
    "sku": "SAMPLE001",
    "price": 19.99,
    "stock_quantity": 50,
    "min_stock_level": 5
}
product_response = requests.post(f"{BASE_URL}/products/", json=product_data, headers=headers)
print(product_response.json())

# Get dashboard summary
dashboard_response = requests.get(f"{BASE_URL}/dashboard/summary", headers=headers)
print(dashboard_response.json())
```

## Error Handling

The API uses standard HTTP status codes and returns error details in JSON format:

```json
{
  "detail": "Error message description"
}
```

Common status codes:
- `200`: Success
- `201`: Created
- `400`: Bad Request (validation errors)
- `401`: Unauthorized (invalid or missing token)
- `403`: Forbidden (insufficient permissions)
- `404`: Not Found
- `500`: Internal Server Error

## Security Features

- **JWT Authentication**: Secure token-based authentication
- **Password Hashing**: Bcrypt hashing for password security
- **Role-Based Access Control**: Different permission levels for different user roles
- **Input Validation**: Pydantic models ensure data validation
- **CORS Support**: Configurable CORS for web applications

## Performance Considerations

- **MongoDB Indexing**: Consider adding indexes on frequently queried fields:
  ```javascript
  // Recommended indexes
  db.users.createIndex({"username": 1})
  db.users.createIndex({"email": 1})
  db.products.createIndex({"sku": 1})
  db.products.createIndex({"barcode": 1})
  db.sales.createIndex({"created_at": -1})
  db.sales.createIndex({"customer_id": 1})
  ```

- **Connection Pooling**: MongoDB connection pool is configured for optimal performance
- **Async Operations**: All database operations are asynchronous for better performance

## Deployment

### Using Docker (Optional)

Create a `Dockerfile`:
```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["python", "main.py"]
```

### Production Considerations

1. **Environment Variables**: Use proper environment variables for production
2. **Secret Key**: Generate a strong secret key for JWT
3. **Database Security**: Ensure MongoDB is properly secured
4. **HTTPS**: Use HTTPS in production
5. **Logging**: Configure proper logging for production
6. **Monitoring**: Add health checks and monitoring

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is licensed under the MIT License.

## Support

For support and questions, please create an issue in the repository or contact the development team.
```
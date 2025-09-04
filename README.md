# Inventory Management System

A comprehensive FastAPI-based inventory management system with MongoDB backend, featuring product management, point-of-sale operations, customer management, and business analytics.

## Features

- **Product Management**: Complete product catalog with categories, suppliers, and stock tracking
- **Point of Sale (POS)**: Full POS system for sales transactions
- **Customer Management**: Customer profiles and relationship management
- **Order Management**: Order processing and tracking
- **Expense Tracking**: Business expense management and categorization
- **Dashboard & Analytics**: Business insights and reporting
- **User Authentication**: Secure user management with role-based access
- **Installment Plans**: Payment plan management
- **Multi-tenant Support**: Support for multiple business locations

## Tech Stack

- **Backend**: FastAPI (Python 3.11+)
- **Database**: MongoDB with Motor (async driver)
- **Authentication**: JWT with bcrypt password hashing
- **Frontend**: Jinja2 templates with static file serving
- **File Storage**: Cloudinary integration for image management
- **Email**: FastAPI-Mail for notifications
- **Containerization**: Docker & Docker Compose

## Quick Start

### Prerequisites

- Python 3.11+
- MongoDB instance (local or Atlas)
- Docker (optional)

### Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd inventory
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure environment variables:
```bash
# Copy and modify the configuration in app/config/settings.py
# Set your MongoDB connection details
```

4. Run the application:
```bash
python start.py
```

The application will be available at:
- API: http://localhost:8000
- Interactive API Docs: http://localhost:8000/docs
- ReDoc Documentation: http://localhost:8000/redoc

### Docker Deployment

1. Build and run with Docker Compose:
```bash
docker-compose up -d
```

The application will be available at http://localhost:8001

## API Endpoints

The system provides comprehensive RESTful APIs with detailed functionality:

### Authentication & Authorization (`/api/auth`)
- `POST /login` - Authenticate user credentials and return JWT access token for session management
- `GET /me` - Retrieve current authenticated user's profile information and permissions
- `POST /change-password` - Update user password with current password verification
- `POST /forgot-password` - Generate and send password reset token via email to user
- `POST /reset-password` - Reset user password using valid reset token from email
- `GET /ping` - Test endpoint for base URL detection and system health check

### User Management (`/api/users`)
- `GET /` - List all system users with pagination and role filtering (admin only)
- `POST /` - Create new user account with role assignment (admin/manager only)
- `GET /{user_id}` - Retrieve specific user details and permissions
- `PUT /{user_id}` - Update user information including roles and status
- `DELETE /{user_id}` - Deactivate user account (soft delete)

### Product Management (`/api/products`)
- `GET /` - List products with advanced filtering (category, supplier, stock status, price range)
- `POST /` - Create new product with automatic supplier linking and stock initialization
- `GET /{product_id}` - Get detailed product information including scent profiles and stock history
- `PUT /{product_id}` - Update product details with automatic change logging
- `DELETE /{product_id}` - Remove product from catalog (soft delete with stock validation)
- `POST /{product_id}/restock` - Add stock quantity with supplier tracking and expense recording
- `POST /{product_id}/upload-image` - Upload product image to Cloudinary with automatic optimization
- `DELETE /{product_id}/image` - Remove product image from Cloudinary storage
- `GET /stats` - Generate product statistics for dashboard (total count, low stock alerts, categories)
- `GET /check-name/{name}` - Validate product name uniqueness before creation
- `GET /suppliers/dropdown` - Get active suppliers list for product creation forms
- `POST /{product_id}/open-bottle` - Open new bottle for decant products with quantity tracking
- `GET /{product_id}/decant-info` - Get decant availability and bottle status information

### Customer Management (`/api/customers`)
- `GET /` - List customers with search, pagination, and activity filtering
- `POST /` - Create new customer profile with contact validation and duplicate checking
- `GET /{customer_id}` - Retrieve customer details with purchase history summary
- `PUT /{customer_id}` - Update customer information with change audit trail
- `DELETE /{customer_id}` - Remove customer (with order history preservation)
- `GET /{customer_id}/orders` - Get customer's complete order history with pagination
- `GET /stats` - Generate customer analytics (total count, new customers, top buyers)
- `GET /table` - Get customers formatted for data table display with sorting
- `GET /export/vcf` - Export all customers as VCF contact file for phone/email import

### Point of Sale (`/api/pos`)
- `POST /sales` - Process complete sale transaction with inventory updates and receipt generation
- `GET /sales` - List sales with filtering by date, customer, payment method, and amount
- `GET /products/search` - Real-time product search for POS with stock availability
- `GET /customers/search` - Quick customer lookup for POS transactions
- `POST /customers` - Create new customer directly from POS interface
- `POST /orders` - Create order from POS that generates both order and sale records
- `GET /debug/test-connection` - Verify POS system connectivity and database access

### Order Management (`/api/orders`)
- `GET /` - List orders with status filtering, date ranges, and customer search
- `POST /` - Create new order with automatic stock reservation
- `GET /{order_id}` - Get complete order details including items and payment status
- `PUT /{order_id}` - Update order with automatic stock adjustment and change tracking
- `DELETE /{order_id}` - Cancel order with stock restoration and notification

### Categories (`/api/categories`)
- `GET /` - List product categories with hierarchical structure and product counts
- `POST /` - Create new category with parent-child relationship support
- `PUT /{category_id}` - Update category details with product reassignment
- `DELETE /{category_id}` - Remove category with product migration to parent category

### Suppliers (`/api/suppliers`)
- `GET /` - List suppliers with contact information and product associations
- `POST /` - Create new supplier with contact validation and duplicate prevention
- `PUT /{supplier_id}` - Update supplier information with product price updates
- `DELETE /{supplier_id}` - Remove supplier with product reassignment handling

### Expenses (`/api/expenses`)
- `GET /` - List expenses with category filtering, date ranges, and amount sorting
- `POST /` - Record new expense with automatic categorization and receipt upload
- `PUT /{expense_id}` - Update expense details with approval workflow
- `DELETE /{expense_id}` - Remove expense record with audit trail

### Dashboard & Analytics (`/api/dashboard`)
- `GET /stats` - Comprehensive business statistics (sales, revenue, inventory, customers)
- `GET /sales-summary` - Sales performance metrics with period comparisons
- `GET /top-products` - Best-selling products analysis with revenue contribution
- `GET /revenue-trends` - Revenue analysis with growth trends and forecasting

### Installments (`/api/installments`)
- `GET /` - List installment plans with payment status and customer information
- `POST /` - Create installment plan with payment schedule generation
- `PUT /{installment_id}` - Update installment terms with payment recalculation
- `POST /{installment_id}/payment` - Record installment payment with balance updates

## Project Structure

```
inventory/
├── app/
│   ├── config/          # Application configuration
│   ├── middleware/      # Custom middleware
│   ├── models/          # Database models
│   ├── routes/          # API route handlers
│   ├── schemas/         # Pydantic schemas
│   ├── services/        # Business logic
│   ├── static/          # Static files
│   ├── templates/       # Jinja2 templates
│   └── utils/           # Utility functions
├── main.py              # FastAPI application
├── start.py             # Application startup script
├── requirements.txt     # Python dependencies
├── Dockerfile           # Docker configuration
└── docker-compose.yml   # Docker Compose setup
```

## Configuration

Key configuration options in `app/config/settings.py`:

- MongoDB connection settings
- JWT authentication settings
- Email configuration
- File upload settings
- Application environment settings

## Development

### Running Tests

```bash
pytest
```

### Code Style

The project follows Python best practices with:
- Async/await patterns for database operations
- Pydantic models for data validation
- Structured logging
- Error handling middleware

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

[Add your license information here]

## Support

For support and questions, please [create an issue](../../issues) in the repository.

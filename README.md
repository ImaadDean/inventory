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

The system provides RESTful APIs for:

- `/auth/*` - Authentication and authorization
- `/users/*` - User management
- `/products/*` - Product catalog management
- `/customers/*` - Customer management
- `/categories/*` - Product categorization
- `/suppliers/*` - Supplier management
- `/expenses/*` - Expense tracking
- `/pos/*` - Point of sale operations
- `/orders/*` - Order management
- `/dashboard/*` - Analytics and reporting
- `/installments/*` - Payment plan management

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

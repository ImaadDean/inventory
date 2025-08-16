# Use Python base image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements first for caching
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the app
COPY . .

# Expose port 8001
EXPOSE 8001

# Start the app
CMD ["python", "start.py"]

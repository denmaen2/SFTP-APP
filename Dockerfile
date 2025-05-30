FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    openssh-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements-minimal.txt .
RUN pip install -r requirements-minimal.txt

# Install plotext for terminal dashboard
RUN pip install plotext

# Copy application files
COPY *.py ./
COPY . .

# Create the terminal dashboard script in the container
COPY terminal_dashboard.py ./

# Create data directory
RUN mkdir -p /app/data

# Set proper permissions
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE 5000

# Default command runs the web app, but can be overridden
CMD ["python", "app_collector.py"]

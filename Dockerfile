# Use an official slim Python image as a base
FROM python:3.11-slim

# Set working directory inside the container
WORKDIR /app

# Copy dependency file first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies without caching to keep image small
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Set environment variables for better performance
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Expose the default port used by the Django app
EXPOSE 8000

RUN python manage.py collectstatic --noinput

# Run the application using Gunicorn WSGI server
CMD ["gunicorn", "HotelBookingAPI.wsgi:application", "--bind", "0.0.0.0:8000"]

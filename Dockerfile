# Use the official Python image for ARM64
FROM python:3.12-slim

# Set the working directory in the container
WORKDIR /app

# Install build dependencies
RUN apt-get update && \
    apt-get install -y gcc python3-dev && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml poetry.lock /app/

# Install poetry and project dependencies
RUN pip install --no-cache-dir poetry && \
    poetry config virtualenvs.create false && \
    poetry install --only main

# Copy the rest of the application code into the container
COPY . /app/

RUN mkdir /data

EXPOSE 5000

CMD ["python", "-m", "geo_activity_playground", "--basedir", "/data", "serve", "--host", "0.0.0.0"]



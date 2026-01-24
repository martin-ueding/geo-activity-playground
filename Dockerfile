# Use the official Python image for ARM64
FROM python:3.12-slim

# Set the working directory in the container
WORKDIR /app

# Install build dependencies
RUN apt-get update && \
    apt-get install -y gcc python3-dev && \
    rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY pyproject.toml uv.lock /app/

# Install project dependencies
RUN uv sync --frozen --no-dev --no-install-project

# Copy the rest of the application code into the container
COPY . /app/

# Install the actual project.
RUN uv sync --frozen --no-dev

RUN mkdir /data

EXPOSE 5000

CMD ["uv", "run", "python", "-m", "geo_activity_playground", "--basedir", "/data", "serve", "--host", "0.0.0.0"]



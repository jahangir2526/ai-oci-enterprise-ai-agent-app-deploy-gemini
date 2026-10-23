FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /bin/uv

WORKDIR /app

# Install locked runtime dependencies separately for Docker layer caching.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project --no-cache

COPY main.py .

# Use the environment created by uv without syncing at container startup.
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8080

CMD ["python", "main.py"]

FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Cache dependency installation separately from application code.
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt

RUN useradd --no-create-home --uid 1000 appuser
COPY main.py .
USER appuser

ENV HOME=/tmp \
    TMPDIR=/tmp \
    XDG_CACHE_HOME=/tmp/.cache

EXPOSE 8080

CMD ["python", "main.py"]

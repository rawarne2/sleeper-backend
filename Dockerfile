# Debian slim (glibc): manylinux wheels for rpds-py, psycopg2-binary, greenlet, etc.
# work reliably on linux/amd64 and linux/arm64 (Apple Silicon). Alpine/musl often forces
# source builds for Rust extensions like rpds-py.
FROM python:3.13.2-slim-bookworm
WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    libpq-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x startup.sh

EXPOSE 5001

CMD ["./startup.sh"]

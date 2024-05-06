FROM python:3.12.3-slim-bookworm AS builder

WORKDIR /src
RUN pip install poetry
COPY pyproject.toml poetry.lock .
RUN poetry export --without-hashes --format requirements.txt > requirements.txt

# ===========================

FROM python:3.12.3-slim-bookworm

WORKDIR /src

COPY --from=builder /src/requirements.txt .

RUN apt-get update && \
    apt-get upgrade -y && \
    pip install -r requirements.txt && \
    rm -rf requirements.txt /var/lib/apt/lists/* /tmp/*

COPY ./hushline ./hushline
COPY ./migrations ./migrations

ENV FLASK_APP='hushline:app'

CMD gunicorn --bind 0.0.0.0:8080 -w 2 \
        --capture-output --access-logformat '%(r)s %(s)s' \
        --forwarded-allow-ips '0.0.0.0' \
        'hushline:app'

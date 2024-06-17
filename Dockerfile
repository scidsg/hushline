FROM python:3.12-bookworm as base
WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y --no-install-recommends \
    build-essential curl libpcsclite-dev clang llvm pkg-config nettle-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install poetry

# Install Rust (for SequoiaPGP)
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

# Install Poetry dependencies
COPY poetry.lock pyproject.toml /app/
RUN poetry install --no-root

# Copy the rest of the application
COPY . /app

FROM base as test

RUN . ./dev_env.sh && poetry run pytest -vv /app/tests

FROM base as app

# Buildkit will skip the test stage unless we have an explicit dependency on it
COPY --from=test /app/README.md /app

# Expose port 8080
EXPOSE 8080

# Run!
ENV FLASK_APP="hushline"
CMD ["./start.sh"]

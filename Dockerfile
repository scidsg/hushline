FROM python:3.12-bookworm
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
RUN poetry install

# Copy the rest of the application
COPY . /app

# Expose port 5000
EXPOSE 5000

# Run!
ENV FLASK_APP="hushline"
CMD ["poetry", "run", "flask", "run", "-p", "5000", "--host", "0.0.0.0"]

FROM python:3.12.3-bullseye

WORKDIR /src

# Install necessary system packages for both Rust, Python, and required libraries
RUN apt-get update && \
    apt-get install -y curl gcc libc6-dev libpq-dev build-essential \
    pkg-config libpcsclite-dev nettle-dev clang-11 libclang-11-dev redis-server && \
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y

# Start Redis server in the background
RUN service redis-server start

# Ensure Rust is on the PATH and confirm it
ENV PATH="/root/.cargo/bin:$PATH"
RUN cargo --version && clang-11 --version

# Set LIBCLANG_PATH directly in the RUN command
ENV LIBCLANG_PATH="/usr/lib/llvm-11/lib"
RUN echo "LIBCLANG_PATH is set to $LIBCLANG_PATH" && find /usr/lib /usr/local/lib -type f -name "libclang*.so" -exec echo "libclang found at: {}" \;

# Setup PKG_CONFIG_PATH for pkg-config to find nettle
ENV PKG_CONFIG_PATH="/usr/lib/x86_64-linux-gnu/pkgconfig"

# Install Poetry
RUN pip install poetry

# Copy pyproject.toml and poetry.lock from the project root, assuming Docker build is run from the project root
COPY pyproject.toml poetry.lock ./

# Export Python package requirements from Poetry and install them
RUN poetry export --without-hashes --format requirements.txt > requirements.txt && \
    pip install -r requirements.txt

# Clean up to reduce image size
RUN apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Copy the rest of the application from the project root
COPY hushline ./hushline
COPY migrations ./migrations

ENV FLASK_APP='hushline:app'

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "-w", "2", "--capture-output", "--access-logformat", "%(r)s %(s)s", "--forwarded-allow-ips", "0.0.0.0", "hushline:create_app()"]

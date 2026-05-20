# ==========================================
# Stage 1: Build the React Frontend
# ==========================================
FROM oven/bun:alpine AS frontend-builder

WORKDIR /app/web

# Copy dependency files first for layer caching
COPY apps/web/package.json apps/web/bun.lock ./
RUN bun install --frozen-lockfile

# Copy source and build
COPY apps/web/ ./
RUN bun run build

# ==========================================
# Stage 2: Final Image (Python + Postgres + Nginx + Supervisor)
# ==========================================
FROM python:3.13-alpine

# Prevent interactive prompts during package install
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV DATABASE_URL="postgresql://postgres:postgres@localhost:5432/postgres"

# Install system dependencies
RUN apk add --no-cache \
    postgresql \
    nginx \
    supervisor \
    && rm -rf /var/cache/apk/* /tmp/* /root/.cache \
    && mkdir -p /var/log/supervisor /run/postgresql \
    && chown -R postgres:postgres /run/postgresql

# Install uv
RUN pip install --no-cache-dir uv \
    && rm -rf /root/.cache /tmp/*

# --- PostgreSQL Setup ---
RUN mkdir -p /var/lib/postgresql/data \
    && chown -R postgres:postgres /var/lib/postgresql/data \
    && su - postgres -s /bin/sh -c "/usr/bin/initdb -D /var/lib/postgresql/data" \
    && sed -i "s/#listen_addresses = 'localhost'/listen_addresses = '127.0.0.1'/g" /var/lib/postgresql/data/postgresql.conf \
    && echo "host all all 127.0.0.1/32 trust" >> /var/lib/postgresql/data/pg_hba.conf

# --- Backend Setup ---
WORKDIR /app/server
COPY apps/server/pyproject.toml apps/server/uv.lock ./
COPY apps/server/main.py ./
RUN uv sync --frozen \
    && rm -rf /root/.cache /tmp/*

# --- Frontend Static Files ---
COPY --from=frontend-builder /app/web/dist /usr/share/nginx/html

# --- Nginx Setup ---
RUN rm -f /etc/nginx/http.d/default.conf || true
COPY nginx.conf /etc/nginx/http.d/default.conf

# --- Supervisor Setup ---
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

EXPOSE 80

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]

# The agent writes and runs its own code. Run it here, not on your machine.

# The studio's web UI, built once and served by the API.
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 stem

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY stem ./stem
COPY studio ./studio
COPY tests ./tests
COPY pytest.ini ./
COPY --from=web /web/dist ./web/dist

USER stem
ENTRYPOINT ["python", "-m", "stem"]
CMD ["--help"]

FROM node:20-bookworm-slim

RUN apt-get update \
  && apt-get install -y --no-install-recommends git ca-certificates \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .

# Default: offline self-check (no remote pages)
CMD ["node", "scripts/self-check.js", "--m0", "--skip-remote"]


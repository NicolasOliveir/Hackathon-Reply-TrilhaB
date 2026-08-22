FROM mcr.microsoft.com/playwright:v1.62.0-noble

WORKDIR /e2e

COPY tests/e2e/package.json tests/e2e/package-lock.json ./
RUN npm ci --omit=dev

COPY tests/e2e/e2e.mjs ./e2e.mjs

CMD ["node", "e2e.mjs"]

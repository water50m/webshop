FROM node:22-bookworm-slim AS dependencies

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-bookworm-slim AS builder

WORKDIR /app
ARG API_INTERNAL_URL=http://backend:8010
ENV NEXT_TELEMETRY_DISABLED=1 \
    API_INTERNAL_URL=${API_INTERNAL_URL}
COPY --from=dependencies /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22-bookworm-slim AS runner

WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    API_INTERNAL_URL=http://backend:8010
COPY --from=builder /app/package.json /app/package-lock.json ./
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next ./.next

EXPOSE 3000

CMD ["npm", "start"]

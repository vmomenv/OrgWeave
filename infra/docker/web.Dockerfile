FROM node:20-alpine AS deps

RUN corepack enable && corepack prepare pnpm@9.15.9 --activate
WORKDIR /repo

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/package.json
COPY packages/shared-types/package.json packages/shared-types/package.json
RUN pnpm install --frozen-lockfile

FROM node:20-alpine AS builder

RUN corepack enable && corepack prepare pnpm@9.15.9 --activate
WORKDIR /repo

ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
ARG NEXT_PUBLIC_WS_BASE_URL=ws://localhost:8000/ws/v1
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL} \
    NEXT_PUBLIC_WS_BASE_URL=${NEXT_PUBLIC_WS_BASE_URL} \
    NEXT_TELEMETRY_DISABLED=1

COPY --from=deps /repo /repo
COPY . .
RUN pnpm --filter @orgweave/web build

FROM node:20-alpine AS runner

WORKDIR /repo/apps/web
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1

COPY --from=builder /repo /repo
COPY --from=builder /repo/apps/web/.next /repo/apps/web/.next

EXPOSE 3000

CMD ["node", "node_modules/next/dist/bin/next", "start", "-p", "3000"]

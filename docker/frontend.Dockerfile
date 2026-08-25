# Meta2bAnalyst frontend: build with Vite, serve the static bundle with nginx.

# Node 22: Vite 8 requires Node >= 20.19 (or >= 22.12). The previous node:18
# base could not build this frontend at all.
FROM node:22-alpine AS builder

WORKDIR /app

# Install dependencies from the lockfile first so that source edits do not
# invalidate the dependency layer.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --prefer-offline --no-audit --fund=false

COPY frontend/ ./

# `npm run build` runs `tsc -b && vite build`, so a type error fails the image
# build rather than shipping a broken bundle.
RUN npm run build


FROM nginx:alpine

# apache2-utils provides htpasswd; nginx:alpine ships neither it nor openssl,
# and the access-gate entrypoint needs one of them for ACCESS_PASSWORD.
RUN apk add --no-cache apache2-utils

COPY --from=builder /app/dist /usr/share/nginx/html
# Both config variants are baked in; the entrypoint picks one at start.
COPY docker/nginx.conf /etc/nginx/conf.d/open.conf
COPY docker/nginx-auth.conf /etc/nginx/conf.d/auth.conf
COPY docker/frontend-entrypoint.sh /docker-entrypoint-m2b.sh
RUN chmod +x /docker-entrypoint-m2b.sh

EXPOSE 80

# 127.0.0.1, not localhost: in the alpine image localhost can resolve to ::1
# while nginx listens on IPv4 only, so the healthcheck connection is refused.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://127.0.0.1/nginx-health || exit 1

CMD ["/docker-entrypoint-m2b.sh"]

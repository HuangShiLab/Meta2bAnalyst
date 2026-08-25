#!/bin/sh
# Meta2bAnalyst frontend entrypoint: optionally gate the app behind HTTP
# basic auth (for shared intranet deployments, e.g. a class of students),
# then hand over to nginx.
#
#   ACCESS_PASSWORD  if non-empty, auth is ON with this password
#   ACCESS_USER      username, defaults to "student"
#
# Without ACCESS_PASSWORD the container behaves exactly as before (open,
# localhost-only is then the deployer's port-binding choice).
set -eu

if [ -n "${ACCESS_PASSWORD:-}" ]; then
    user="${ACCESS_USER:-student}"
    # htpasswd comes from apache2-utils (installed in the final stage).
    htpasswd -bc /etc/nginx/.htpasswd "$user" "$ACCESS_PASSWORD" >/dev/null
    # 644 not 640: nginx workers run as the nginx user and must be able to
    # read the file, or every authenticated request fails with a 500.
    chmod 644 /etc/nginx/.htpasswd
    cp /etc/nginx/conf.d/auth.conf /etc/nginx/conf.d/default.conf
    echo "[entrypoint] access gate ON (user: $user)"
else
    cp /etc/nginx/conf.d/open.conf /etc/nginx/conf.d/default.conf
    echo "[entrypoint] access gate OFF (ACCESS_PASSWORD not set)"
fi

exec nginx -g 'daemon off;'

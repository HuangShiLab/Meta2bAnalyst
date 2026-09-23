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

# nginx loads EVERY *.conf in conf.d/, so open.conf and auth.conf must not
# both stay there -- with both present, the first one alphabetically (auth.conf)
# captures every request whose Host does not literally match "localhost",
# gating the whole site behind basic auth even when no password is set.
confd=/etc/nginx/conf.d
if [ -n "${ACCESS_PASSWORD:-}" ]; then
    user="${ACCESS_USER:-student}"
    # htpasswd comes from apache2-utils (installed in the final stage).
    htpasswd -bc /etc/nginx/.htpasswd "$user" "$ACCESS_PASSWORD" >/dev/null
    # 644 not 640: nginx workers run as the nginx user and must be able to
    # read the file, or every authenticated request fails with a 500.
    chmod 644 /etc/nginx/.htpasswd
    cp "$confd/auth.conf" "$confd/default.conf"
    echo "[entrypoint] access gate ON (user: $user)"
else
    cp "$confd/open.conf" "$confd/default.conf"
    echo "[entrypoint] access gate OFF (ACCESS_PASSWORD not set)"
fi
rm -f "$confd/open.conf" "$confd/auth.conf"

exec nginx -g 'daemon off;'

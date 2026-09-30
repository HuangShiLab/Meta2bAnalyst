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
#
# Templates live at /etc/nginx/templates (a read-only image layer). The
# entrypoint regenerates default.conf from them on EVERY start and never
# modifies the templates, so container restarts work: earlier versions
# deleted the conf.d copies after the first start and crash-looped on the
# next one ("cp: can't stat .../open.conf").
confd=/etc/nginx/conf.d
templates=/etc/nginx/templates
if [ -n "${ACCESS_PASSWORD:-}" ]; then
    user="${ACCESS_USER:-student}"
    # htpasswd comes from apache2-utils (installed in the final stage).
    htpasswd -bc /etc/nginx/.htpasswd "$user" "$ACCESS_PASSWORD" >/dev/null
    # 644 not 640: nginx workers run as the nginx user and must be able to
    # read the file, or every authenticated request fails with a 500.
    chmod 644 /etc/nginx/.htpasswd
    src="$templates/auth.conf"; [ -f "$src" ] || src="$confd/auth.conf"
    echo "[entrypoint] access gate ON (user: $user)"
else
    src="$templates/open.conf"; [ -f "$src" ] || src="$confd/open.conf"
    echo "[entrypoint] access gate OFF (ACCESS_PASSWORD not set)"
fi
rm -f "$confd/default.conf"
cp "$src" "$confd/default.conf"
# Drop any variant that ships directly in conf.d (old image layout): nginx
# would load it next to default.conf.
rm -f "$confd/open.conf" "$confd/auth.conf"

exec nginx -g 'daemon off;'

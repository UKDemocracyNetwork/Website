ARG GHOST_VERSION=6.74.0
FROM ghost:${GHOST_VERSION}-alpine

# Copy startup validation script
COPY docker/ghost/validate.sh /usr/local/bin/validate.sh

# Copy custom theme
COPY theme/ /var/lib/ghost/content/themes/dn-theme/

# Routing config (e.g. /bulletin/<slug>/). Ghost reads content/settings/routes.yaml
# on boot. Locally this path is bind-mounted (docker-compose); for deploys it is
# baked into the image here. The Admin API does not expose routes upload.
COPY routes.yaml /var/lib/ghost/content/settings/routes.yaml

ENTRYPOINT ["/usr/local/bin/validate.sh"]
CMD ["node", "current/index.js"]

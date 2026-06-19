ARG GHOST_VERSION=5
# Pin this to a specific version before deploying, e.g. ARG GHOST_VERSION=5.114.1
FROM ghost:${GHOST_VERSION}-alpine

# Install ghos3 S3 adapter (AWS SDK v3, Ghost 5.x) for deployed environments (not used in local dev)
# Installation method per ghos3 README: bootstrap package, copy source, then install deps in-place
RUN mkdir -p /var/lib/ghost/content/adapters/storage/s3 && \
    mkdir /tmp/ghos3-bootstrap && \
    cd /tmp/ghos3-bootstrap && \
    npm install ghos3 && \
    cp -r node_modules/ghos3/. /var/lib/ghost/content/adapters/storage/s3/ && \
    rm -rf /tmp/ghos3-bootstrap && \
    cd /var/lib/ghost/content/adapters/storage/s3 && \
    npm install --production

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

#!/bin/sh
set -e

if [ "$NODE_ENV" = "production" ]; then
    echo "Validating required environment variables..."
    REQUIRED="url database__client database__connection__host database__connection__user database__connection__password database__connection__database"
    MISSING=""
    for var in $REQUIRED; do
        eval val=\$$var
        if [ -z "$val" ]; then
            MISSING="$MISSING $var"
        fi
    done
    if [ -n "$MISSING" ]; then
        echo "ERROR: Missing required environment variables:$MISSING" >&2
        exit 1
    fi
    echo "All required environment variables present."
fi

exec docker-entrypoint.sh "$@"

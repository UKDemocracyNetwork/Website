#!/usr/bin/env bash
# Manage the Ghost stack on the Lightsail server. Used by CI and by hand.
#
#   scripts/lightsail.sh deploy IMAGE DOMAIN        Start this release of the stack
#   scripts/lightsail.sh restore IMAGE DOMAIN SQL_GZ CONTENT_TGZ
#                                                   Replace all data, then start
#   scripts/lightsail.sh run COMMAND                Run a command on the server
#
# No SSH key or AWS credential is stored anywhere. Each run asks Lightsail for a
# short-lived SSH certificate and opens port 22 to this machine's IP address only,
# closing it again on exit. The server gets a temporary ECR token over SSH too.
set -euo pipefail

INSTANCE="${LIGHTSAIL_INSTANCE:-dn-website-ghost}"
REGION="${AWS_REGION:-eu-west-2}"
REMOTE_DIR=/opt/ghost
COMPOSE="docker compose --env-file secrets.env --env-file release.env"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

WORK_DIR="$(mktemp -d)"
PORT_OPENED=""

cleanup() {
  if [ -n "$PORT_OPENED" ]; then
    aws lightsail close-instance-public-ports --region "$REGION" --instance-name "$INSTANCE" \
      --port-info "fromPort=22,toPort=22,protocol=tcp,cidrs=$PORT_OPENED" >/dev/null ||
      echo "WARNING: could not close port 22 for $PORT_OPENED" >&2
  fi
  rm -rf "$WORK_DIR"
}
trap cleanup EXIT

connect() {
  local details
  details="$(aws lightsail get-instance-access-details --region "$REGION" --instance-name "$INSTANCE" \
    --protocol ssh --output json)"
  HOST="$(jq -r .accessDetails.ipAddress <<<"$details")"
  USER_NAME="$(jq -r .accessDetails.username <<<"$details")"
  jq -r .accessDetails.privateKey <<<"$details" >"$WORK_DIR/key"
  jq -r .accessDetails.certKey <<<"$details" >"$WORK_DIR/key-cert.pub"
  chmod 600 "$WORK_DIR/key"
  jq -r --arg host "$HOST" '.accessDetails.hostKeys[] | "\($host) \(.algorithm) \(.publicKey)"' \
    <<<"$details" >"$WORK_DIR/known_hosts"

  SSH_OPTS=(-i "$WORK_DIR/key" -o "CertificateFile=$WORK_DIR/key-cert.pub"
    -o "UserKnownHostsFile=$WORK_DIR/known_hosts" -o StrictHostKeyChecking=yes
    -o IdentitiesOnly=yes -o ConnectTimeout=10 -o ServerAliveInterval=30)

  PORT_OPENED="$(curl -fsS -4 https://checkip.amazonaws.com | tr -d '[:space:]')/32"
  aws lightsail open-instance-public-ports --region "$REGION" --instance-name "$INSTANCE" \
    --port-info "fromPort=22,toPort=22,protocol=tcp,cidrs=$PORT_OPENED" >/dev/null

  # The firewall change takes a moment to apply.
  for _ in $(seq 1 30); do
    if ssh -n "${SSH_OPTS[@]}" "$USER_NAME@$HOST" test -f "$REMOTE_DIR/.first-boot-complete" 2>/dev/null; then
      return 0
    fi
    sleep 10
  done
  echo "ERROR: server not reachable, or first boot not finished" >&2
  return 1
}

remote() {
  ssh "${SSH_OPTS[@]}" "$USER_NAME@$HOST" "cd $REMOTE_DIR && $1"
}

# Copy the stack definition to the server and record which release it should run.
sync_release() {
  local image="$1" domain="$2"
  scp "${SSH_OPTS[@]}" "$REPO_ROOT/deploy/compose.yml" "$REPO_ROOT/deploy/nginx.conf.template" \
    "$USER_NAME@$HOST:$REMOTE_DIR/" >/dev/null
  printf 'GHOST_IMAGE=%s\nGHOST_DOMAIN=%s\n' "$image" "$domain" | remote "cat > release.env"
}

pull_images() {
  local image="$1" registry="${1%%/*}"
  aws ecr get-login-password --region "$REGION" |
    remote "docker login --username AWS --password-stdin $registry >/dev/null 2>&1"
  remote "$COMPOSE -f compose.yml pull --quiet; status=\$?; docker logout $registry >/dev/null; exit \$status"
}

wait_until_serving() {
  # A database upgrade on first start of a new Ghost version can take a few minutes.
  for _ in $(seq 1 36); do
    if remote "curl -fsS -o /dev/null --max-time 10 http://localhost/" 2>/dev/null; then
      echo "Ghost is serving."
      return 0
    fi
    sleep 10
  done
  remote "$COMPOSE -f compose.yml ps; $COMPOSE -f compose.yml logs --tail=40 ghost" || true
  echo "ERROR: Ghost did not start" >&2
  return 1
}

start_stack() {
  remote "$COMPOSE -f compose.yml up -d --remove-orphans --wait --wait-timeout 120 mysql"
  remote "$COMPOSE -f compose.yml up -d --remove-orphans"
  wait_until_serving
  remote "docker image prune -af --filter until=168h >/dev/null"
}

cmd_deploy() {
  local image="$1" domain="$2"
  connect
  sync_release "$image" "$domain"
  pull_images "$image"
  start_stack
}

cmd_restore() {
  local image="$1" domain="$2" sql="$3" content="$4"
  [ -f "$sql" ] && [ -f "$content" ] || { echo "ERROR: backup files not found" >&2; exit 1; }
  connect
  sync_release "$image" "$domain"
  pull_images "$image"

  # Ghost stays stopped until the data is in place, so a fresh install's public
  # setup page is never exposed.
  remote "$COMPOSE -f compose.yml stop ghost nginx 2>/dev/null || true"
  remote "$COMPOSE -f compose.yml up --no-start"
  remote "$COMPOSE -f compose.yml up -d --wait --wait-timeout 120 mysql"
  remote "$COMPOSE -f compose.yml exec -T mysql sh -c 'MYSQL_PWD=\"\$MYSQL_ROOT_PASSWORD\" mysql -uroot \
    -e \"DROP DATABASE IF EXISTS ghost; CREATE DATABASE ghost CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;\"'"
  gunzip -c "$sql" | remote "$COMPOSE -f compose.yml exec -T mysql sh -c \
    'MYSQL_PWD=\"\$MYSQL_ROOT_PASSWORD\" mysql -uroot ghost'"
  # Local login sessions mean nothing here.
  remote "$COMPOSE -f compose.yml exec -T mysql sh -c \
    'MYSQL_PWD=\"\$MYSQL_ROOT_PASSWORD\" mysql -uroot ghost -e \"TRUNCATE sessions;\"'"
  remote "docker run --rm -i -v ghost_ghost_images:/c/images -v ghost_ghost_media:/c/media \
    -v ghost_ghost_files:/c/files alpine:3.24 sh -c 'rm -rf /c/images/* /c/media/* /c/files/*; tar -xzf - -C /c'" <"$content"

  start_stack
}

case "${1:-}" in
  deploy) shift; cmd_deploy "$@" ;;
  restore) shift; cmd_restore "$@" ;;
  run) shift; connect; remote "$*" ;;
  *) sed -n '2,6p' "$0" >&2; exit 2 ;;
esac

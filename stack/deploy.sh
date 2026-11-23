#!/usr/bin/env bash
# Copies this stack folder to the Pi and applies it: keeps the Pi's old copy of
# every changed file in backups/<time>/, checks the Home Assistant config before
# anything restarts (and puts the old files back if the check fails), then
# restarts only what the changed files need.
#
#   cp deploy.env.example deploy.env   # once: the Pi's SSH target and folder
#   ./deploy.sh --dry-run              # list what differs
#   ./deploy.sh                        # copy, check, restart
#
# Not copied: .env (secrets, edited on the Pi), Home Assistant's secrets.yaml,
# and anything the containers write (photos, labels, databases).
# docker-compose.yml is copied but never applied: run `docker compose up -d`
# on the Pi yourself after reading the diff.

set -euo pipefail
cd "$(dirname "$0")"

[ -f deploy.env ] && . ./deploy.env
: "${PI:?Set PI=user@host in deploy.env}"
: "${PI_DIR:?Set PI_DIR, the stack folder on the Pi, in deploy.env}"
read -r -a SSH_ARGS <<< "${SSH_OPTS:-}"
ssh_pi() { timeout 300 ssh -o ConnectTimeout=10 "${SSH_ARGS[@]}" "$PI" "$@"; }

DRY_RUN=0
[ "${1:-}" = "--dry-run" ] && DRY_RUN=1

FILES=(
  docker-compose.yml .env.example setup.sh
  frigate/config/config.yml
  mosquitto/config/mosquitto.conf
  homeassistant/configuration.yaml
  homeassistant/secrets.example.yaml
  homeassistant/packages/dog_potty.yaml
  homeassistant/dashboards/potty.yaml
  homeassistant/www/potty-history-card.js
  poop-checker/app.py poop-checker/Dockerfile poop-checker/requirements.txt
  training/train.py
)

# One SSH call for all the hashes on the Pi ("-" when a file is missing there).
remote=$(ssh_pi "cd '$PI_DIR' && for f in ${FILES[*]}; do if [ -f \"\$f\" ]; then sha256sum \"\$f\"; else echo \"- \$f\"; fi; done")
changed=()
for f in "${FILES[@]}"; do
  theirs=$(awk -v f="$f" '$2 == f { print $1 }' <<< "$remote")
  ours=$(sha256sum "$f" | cut -d' ' -f1)
  [ "$ours" != "$theirs" ] && changed+=("$f")
done

if [ ${#changed[@]} -eq 0 ]; then
  echo "The Pi already has this version."
  exit 0
fi
printf 'Differs on the Pi: %s\n' "${changed[@]}"
[ $DRY_RUN -eq 1 ] && exit 0

is_changed() { local f; for f in "${changed[@]}"; do [[ "$f" == $1 ]] && return 0; done; return 1; }

# Home Assistant serves /local files with a 31-day cache. Phones only load a
# new card when configuration.yaml asks for a new ?v=.
if is_changed homeassistant/www/potty-history-card.js && ! is_changed homeassistant/configuration.yaml; then
  echo "potty-history-card.js changed: bump ?v= in homeassistant/configuration.yaml first." >&2
  exit 1
fi

stamp=$(date +%Y%m%d-%H%M%S)
backup="backups/$stamp"
ssh_pi "cd '$PI_DIR' && mkdir -p '$backup' && for f in ${changed[*]}; do
  if [ -f \"\$f\" ]; then mkdir -p '$backup'/\"\$(dirname \"\$f\")\" && cp -p \"\$f\" '$backup'/\"\$f\"; fi; done"
echo "Old copies kept in $PI_DIR/$backup"

# cat into existing files keeps their owner and mode on the Pi. New files take
# the owner of their folder.
for f in "${changed[@]}"; do
  ssh_pi "cd '$PI_DIR' && mkdir -p \"\$(dirname '$f')\" && new=\$([ -f '$f' ] || echo 1) && cat > '$f' && \
    if [ -n \"\$new\" ]; then chown --reference=\"\$(dirname '$f')\" '$f'; chmod $(stat -c %a "$f") '$f'; fi" < "$f"
done
echo "Copied ${#changed[@]} file(s)."

restore() {
  echo "Putting the old files back from $backup." >&2
  ssh_pi "cd '$PI_DIR' && for f in ${changed[*]}; do
    if [ -f '$backup'/\"\$f\" ]; then cat '$backup'/\"\$f\" > \"\$f\"; else rm -f \"\$f\"; fi; done"
}

if is_changed 'homeassistant/*'; then
  echo "Checking the Home Assistant config..."
  if ! ssh_pi "docker exec homeassistant python -m homeassistant --script check_config -c /config" > /tmp/potty-check-config.$$ 2>&1 \
     || grep -qE "Failed config|Invalid config" /tmp/potty-check-config.$$; then
    cat /tmp/potty-check-config.$$ >&2
    rm -f /tmp/potty-check-config.$$
    restore
    exit 1
  fi
  rm -f /tmp/potty-check-config.$$
fi

# A YAML dashboard is read again on the next page load. Everything else in
# Home Assistant (packages, configuration.yaml, the card's ?v=) needs a restart.
if is_changed homeassistant/configuration.yaml || is_changed 'homeassistant/packages/*'; then
  echo "Restarting Home Assistant..."
  ssh_pi "docker restart homeassistant >/dev/null"
fi
if is_changed frigate/config/config.yml; then
  echo "Restarting Frigate..."
  ssh_pi "docker restart frigate >/dev/null"
fi
if is_changed mosquitto/config/mosquitto.conf; then
  echo "Restarting Mosquitto..."
  ssh_pi "docker restart mosquitto >/dev/null"
fi
if is_changed 'poop-checker/*'; then
  echo "Rebuilding the poop checker..."
  ssh_pi "cd '$PI_DIR' && docker compose build -q poop-checker && docker compose up -d poop-checker"
fi
if is_changed docker-compose.yml; then
  echo "docker-compose.yml changed. Review it, then run on the Pi: cd $PI_DIR && docker compose up -d"
fi
if is_changed homeassistant/dashboards/potty.yaml || is_changed homeassistant/www/potty-history-card.js; then
  echo "Phones: pull down to refresh the Potty page (or reopen the app) to load the new page."
fi
echo "Done."

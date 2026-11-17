#!/usr/bin/env bash
# Idempotent VPS bootstrap for makerbooking. Run as root on a freshly-created
# Hetzner (Ubuntu 26.04) server:
#
#   scp scripts/bootstrap_vps.sh root@$VPS_IP:/tmp/
#   ssh root@$VPS_IP "bash /tmp/bootstrap_vps.sh && rm /tmp/bootstrap_vps.sh"
#
# Safe to re-run: every step checks current state and skips if already done.
# Does NOT install application code, NOT write .env, NOT touch DNS.

set -euo pipefail

DEPLOY_USER="deploy"
APP_DIR="/opt/makerbooking"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Must be run as root." >&2
  exit 1
fi

log() { echo "[bootstrap] $*"; }
changed=0

# ── deploy user ──────────────────────────────────────────────────────────────
if ! id "${DEPLOY_USER}" >/dev/null 2>&1; then
  log "creating user ${DEPLOY_USER}"
  adduser --disabled-password --gecos "" "${DEPLOY_USER}"
  changed=1
else
  log "user ${DEPLOY_USER} already exists"
fi

for grp in sudo docker; do
  if ! id -nG "${DEPLOY_USER}" | tr ' ' '\n' | grep -qx "${grp}"; then
    log "adding ${DEPLOY_USER} to group ${grp}"
    # docker group may not exist yet — created by docker install below.
    if getent group "${grp}" >/dev/null 2>&1; then
      usermod -aG "${grp}" "${DEPLOY_USER}"
      changed=1
    else
      log "  group ${grp} doesn't exist yet; will add after install"
    fi
  fi
done

# Copy root's authorized_keys to deploy (Hetzner pre-populates root's from the key
# you selected at server creation).
ssh_dir="/home/${DEPLOY_USER}/.ssh"
if [[ ! -f "${ssh_dir}/authorized_keys" ]]; then
  log "copying authorized_keys to ${DEPLOY_USER}"
  install -d -m 700 -o "${DEPLOY_USER}" -g "${DEPLOY_USER}" "${ssh_dir}"
  install -m 600 -o "${DEPLOY_USER}" -g "${DEPLOY_USER}" \
    /root/.ssh/authorized_keys "${ssh_dir}/authorized_keys"
  changed=1
fi

# ── packages ─────────────────────────────────────────────────────────────────
need_install=()
for pkg in docker.io docker-compose-v2 ufw fail2ban unattended-upgrades curl; do
  if ! dpkg -s "${pkg}" >/dev/null 2>&1; then
    need_install+=("${pkg}")
  fi
done
if [[ ${#need_install[@]} -gt 0 ]]; then
  log "installing: ${need_install[*]}"
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "${need_install[@]}"
  changed=1
else
  log "all required packages already installed"
fi

# Ensure docker group membership now that docker is installed.
if getent group docker >/dev/null 2>&1 \
   && ! id -nG "${DEPLOY_USER}" | tr ' ' '\n' | grep -qx docker; then
  log "adding ${DEPLOY_USER} to docker group"
  usermod -aG docker "${DEPLOY_USER}"
  changed=1
fi

for svc in docker fail2ban; do
  if ! systemctl is-enabled --quiet "${svc}"; then
    log "enabling ${svc}"
    systemctl enable --now "${svc}"
    changed=1
  fi
done

# ── firewall ─────────────────────────────────────────────────────────────────
if ! ufw status | grep -q "Status: active"; then
  log "configuring ufw"
  ufw --force default deny incoming
  ufw --force default allow outgoing
  ufw allow 22/tcp
  ufw allow 80/tcp
  ufw allow 443/tcp
  ufw --force enable
  changed=1
else
  for port in 22 80 443; do
    if ! ufw status | grep -qE "^${port}/tcp .*ALLOW"; then
      log "allowing ${port}/tcp through ufw"
      ufw allow "${port}/tcp"
      changed=1
    fi
  done
fi

# ── SSH hardening ────────────────────────────────────────────────────────────
sshd_changed=0
if grep -qE "^[#[:space:]]*PermitRootLogin[[:space:]]+(yes|prohibit-password|without-password)" /etc/ssh/sshd_config \
   || ! grep -qE "^PermitRootLogin[[:space:]]+no" /etc/ssh/sshd_config; then
  log "disabling root SSH login"
  sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
  sshd_changed=1
fi
if ! grep -qE "^PasswordAuthentication[[:space:]]+no" /etc/ssh/sshd_config; then
  log "disabling SSH password auth"
  sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
  sshd_changed=1
fi
if [[ "${sshd_changed}" -eq 1 ]]; then
  systemctl reload ssh
  changed=1
fi

# ── unattended security updates ──────────────────────────────────────────────
auto_upgrades=/etc/apt/apt.conf.d/20auto-upgrades
desired_auto_upgrades='APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
'
if [[ ! -f "${auto_upgrades}" ]] || [[ "$(cat ${auto_upgrades})" != "${desired_auto_upgrades%$'\n'}" ]]; then
  log "writing ${auto_upgrades}"
  printf '%s' "${desired_auto_upgrades}" > "${auto_upgrades}"
  changed=1
fi

# ── app directories ──────────────────────────────────────────────────────────
for d in \
  "${APP_DIR}" \
  "${APP_DIR}/data" \
  "${APP_DIR}/data/postgres" \
  "${APP_DIR}/data/uploads" \
  "${APP_DIR}/data/caddy" \
  "${APP_DIR}/data/backups" \
  "${APP_DIR}/scripts" \
  "${APP_DIR}/caddy"; do
  if [[ ! -d "${d}" ]]; then
    log "creating ${d}"
    install -d -o "${DEPLOY_USER}" -g "${DEPLOY_USER}" "${d}"
    changed=1
  fi
done
chown -R "${DEPLOY_USER}:${DEPLOY_USER}" "${APP_DIR}"

# ── done ─────────────────────────────────────────────────────────────────────
if [[ "${changed}" -eq 0 ]]; then
  log "no changes — server already bootstrapped"
else
  log "bootstrap complete"
fi

cat <<EOF

Next steps:
  1. Verify SSH as deploy:  ssh deploy@<this-host> "docker ps && id"
  2. SCP your .env to ${APP_DIR}/.env (chmod 600 after).
  3. SCP docker-compose.yml, caddy/Caddyfile, scripts/{deploy,backup}.sh.
  4. Push to GitHub to trigger the first deploy.
EOF

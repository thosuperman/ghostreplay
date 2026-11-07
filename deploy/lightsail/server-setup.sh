#!/usr/bin/env bash
# One-time (idempotent) host setup for GhostReplay Lab on Ubuntu 24.04 LTS.
# Run as root on the instance; provision.sh uploads the deploy/lightsail directory and runs
# it. Safe to run again: every step checks before it changes anything.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
here=$(cd "$(dirname "$0")" && pwd)
UV_VERSION=0.13.7
UV_SHA256=c5221ff41b7892bfc223543883600125f6a47fe845093e0f5bdff4f359196d83
log() { printf '[setup] %s\n' "$*" >&2; }
[ "$(id -u)" = 0 ] || { echo "run as root" >&2; exit 1; }
. /etc/os-release
[ "$ID" = ubuntu ] || { echo "Ubuntu required" >&2; exit 1; }

log "OS packages"
apt-get update -q
apt-get -y -q -o Dpkg::Options::=--force-confold upgrade
apt-get -y -q install ca-certificates curl gnupg debian-keyring debian-archive-keyring \
  apt-transport-https ufw python3 unattended-upgrades
systemctl enable --now unattended-upgrades >/dev/null

log "Caddy (official apt repository)"
if ! command -v caddy >/dev/null; then
  curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/gpg.key \
    | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt \
    -o /etc/apt/sources.list.d/caddy-stable.list
  chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -q
  apt-get -y -q install caddy
  # Until the first release is activated, answer nothing but a 503.
  printf ':80 {\n\trespond "GhostReplay Lab is being deployed" 503\n}\n' > /etc/caddy/Caddyfile
  systemctl reload caddy
fi

log "uv $UV_VERSION (checksum-pinned release binary)"
if [ "$(/usr/local/bin/uv --version 2>/dev/null | cut -d' ' -f2)" != "$UV_VERSION" ]; then
  tmp=$(mktemp -d /tmp/uv.XXXXXX)
  curl -fsSL -o "$tmp/uv.tar.gz" \
    "https://github.com/astral-sh/uv/releases/download/$UV_VERSION/uv-x86_64-unknown-linux-gnu.tar.gz"
  echo "$UV_SHA256  $tmp/uv.tar.gz" | sha256sum -c --quiet
  tar -xzf "$tmp/uv.tar.gz" -C "$tmp"
  install -m 755 "$tmp/uv-x86_64-unknown-linux-gnu/uv" /usr/local/bin/uv
  case "$tmp" in /tmp/uv.*) rm -rf -- "${tmp:?}" ;; esac
fi

log "swap (1 GiB safety margin for a 2 GB instance)"
if ! swapon --show=NAME --noheadings | grep -qx /swapfile; then
  [ -f /swapfile ] || { fallocate -l 1G /swapfile; chmod 600 /swapfile; mkswap /swapfile >/dev/null; }
  swapon /swapfile
  grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
echo 'vm.swappiness=10' > /etc/sysctl.d/60-ghostreplay.conf
sysctl -q -p /etc/sysctl.d/60-ghostreplay.conf

log "service users and directories"
for lab in support devops; do
  id "ghostreplay-$lab" >/dev/null 2>&1 || useradd --system --no-create-home \
    --home-dir /nonexistent --shell /usr/sbin/nologin "ghostreplay-$lab"
  install -d -m 700 -o "ghostreplay-$lab" -g "ghostreplay-$lab" "/var/lib/ghostreplay/$lab"
done
install -d -m 755 /opt/ghostreplay /opt/ghostreplay/releases /var/lib/ghostreplay \
  /etc/ghostreplay /usr/local/lib/ghostreplay
install -d -m 700 /var/backups/ghostreplay /var/cache/ghostreplay-uv
install -m 644 "$here/bin/gr-common.sh" /usr/local/lib/ghostreplay/gr-common.sh
for f in "$here"/bin/gr-*; do
  [[ $f == *.sh ]] || install -m 755 "$f" /usr/local/sbin/
done

log "journald retention"
install -d /etc/systemd/journald.conf.d
printf '[Journal]\nSystemMaxUse=300M\nMaxRetentionSec=30day\n' \
  > /etc/systemd/journald.conf.d/60-ghostreplay.conf
systemctl restart systemd-journald

log "SSH: keys only, no root login"
cat > /etc/ssh/sshd_config.d/10-ghostreplay.conf <<'EOF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
PubkeyAuthentication yes
MaxAuthTries 3
X11Forwarding no
EOF
sshd -t
systemctl reload ssh

log "host firewall (ufw): 22, 80, 443 only"
ufw default deny incoming >/dev/null
ufw default allow outgoing >/dev/null
ufw allow 22/tcp >/dev/null
ufw allow 80/tcp >/dev/null
ufw allow 443/tcp >/dev/null
ufw allow 443/udp >/dev/null
ufw --force enable >/dev/null
ufw status verbose

log "done"

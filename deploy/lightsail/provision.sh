#!/usr/bin/env bash
# Provision the dedicated GhostReplay Lab Lightsail instance (idempotent).
#
#   deploy/lightsail/provision.sh
#
# Creates — only if missing — an SSH key pair, the 2 GB Ubuntu instance, a static IP and the
# firewall rules, then runs server-setup.sh on the instance. Touches no other resources.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
source "$here/config.sh"

account=$(aws --profile "$AWS_PROFILE" sts get-caller-identity --query Account --output text)
log "AWS profile $AWS_PROFILE, account ${account:0:4}****${account: -4}, region $AWS_REGION"

# Bundle sanity check: never provision anything but the approved 2 GB plan.
read -r ram price <<<"$(aws_ls get-bundles --query "bundles[?bundleId=='$GR_BUNDLE'].[ramSizeInGb,price]" --output text)"
[ "$ram" = "2.0" ] || die "bundle $GR_BUNDLE has ${ram:-?} GB RAM; expected 2 GB"
log "bundle $GR_BUNDLE: ${ram} GB RAM, \$$price/month"

# 1. SSH key (private key stays on this machine).
if [ ! -f "$GR_SSH_KEY" ]; then
  log "creating SSH key $GR_SSH_KEY"
  ssh-keygen -q -t ed25519 -N "" -C "$GR_INSTANCE" -f "$GR_SSH_KEY"
fi
if ! aws_ls get-key-pair --key-pair-name "$GR_KEY_PAIR" >/dev/null 2>&1; then
  log "importing key pair $GR_KEY_PAIR"
  aws_ls import-key-pair --key-pair-name "$GR_KEY_PAIR" \
    --public-key-base64 "$(cat "$GR_SSH_KEY.pub")" >/dev/null
  aws_ls tag-resource --resource-name "$GR_KEY_PAIR" --tags "${GR_TAGS[@]}" >/dev/null
fi

# 2. Instance.
if ! aws_ls get-instance --instance-name "$GR_INSTANCE" >/dev/null 2>&1; then
  log "creating instance $GR_INSTANCE ($GR_BUNDLE, $GR_BLUEPRINT, $GR_AZ)"
  aws_ls create-instances --instance-names "$GR_INSTANCE" --availability-zone "$GR_AZ" \
    --blueprint-id "$GR_BLUEPRINT" --bundle-id "$GR_BUNDLE" --key-pair-name "$GR_KEY_PAIR" \
    --ip-address-type ipv4 --tags "${GR_TAGS[@]}" >/dev/null
fi
for _ in $(seq 60); do
  state=$(aws_ls get-instance-state --instance-name "$GR_INSTANCE" --query state.name --output text)
  [ "$state" = running ] && break
  sleep 5
done
[ "$state" = running ] || die "instance did not reach running (state: $state)"

# 3. Static IP.
if ! aws_ls get-static-ip --static-ip-name "$GR_STATIC_IP" >/dev/null 2>&1; then
  log "allocating static IP $GR_STATIC_IP"
  aws_ls allocate-static-ip --static-ip-name "$GR_STATIC_IP" >/dev/null
fi
attached=$(aws_ls get-static-ip --static-ip-name "$GR_STATIC_IP" --query staticIp.attachedTo --output text)
if [ "$attached" != "$GR_INSTANCE" ]; then
  [ "$attached" = None ] || die "static IP is attached to $attached"
  log "attaching $GR_STATIC_IP to $GR_INSTANCE"
  aws_ls attach-static-ip --static-ip-name "$GR_STATIC_IP" --instance-name "$GR_INSTANCE" >/dev/null
fi
ip=$(gr_ip)
log "static IP $ip"

# 4. Lightsail firewall: web open to all; SSH only from the admin address and the
#    Lightsail browser console. This call replaces the instance's whole rule set.
admin=${GR_ADMIN_CIDR:-$(curl -fsS https://checkip.amazonaws.com)/32}
log "firewall: 80/tcp, 443/tcp+udp public; 22/tcp from $admin and lightsail-connect"
aws_ls put-instance-public-ports --instance-name "$GR_INSTANCE" --port-infos \
  "fromPort=80,toPort=80,protocol=tcp,cidrs=0.0.0.0/0" \
  "fromPort=443,toPort=443,protocol=tcp,cidrs=0.0.0.0/0" \
  "fromPort=443,toPort=443,protocol=udp,cidrs=0.0.0.0/0" \
  "fromPort=22,toPort=22,protocol=tcp,cidrs=$admin,cidrListAliases=lightsail-connect" >/dev/null

# 5. Host setup over SSH.
log "waiting for SSH"
for _ in $(seq 40); do
  gr_ssh -o ConnectTimeout=5 -o BatchMode=yes true 2>/dev/null && break
  sleep 5
done
gr_ssh -o BatchMode=yes true || die "SSH to $ip failed"
log "uploading setup files"
gr_ssh 'rm -rf /tmp/gr-setup && mkdir -p /tmp/gr-setup/bin'
gr_scp -q "$here/server-setup.sh" "$GR_SSH_USER@$ip:/tmp/gr-setup/"
gr_scp -q "$here"/bin/gr-* "$GR_SSH_USER@$ip:/tmp/gr-setup/bin/"
log "running server-setup.sh"
gr_ssh 'sudo bash /tmp/gr-setup/server-setup.sh && rm -rf /tmp/gr-setup'
gr_ssh -o BatchMode=yes 'echo "SSH key login still works after hardening"'
log "provisioned $GR_INSTANCE at $ip — next: dns.sh, then deploy.sh"

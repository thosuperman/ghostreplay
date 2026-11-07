# Shared settings for the GhostReplay Lab Lightsail deployment.
# Every value can be overridden from the environment, e.g. AWS_PROFILE=other ./provision.sh
# shellcheck shell=bash disable=SC2034,SC2054

: "${AWS_PROFILE:=hayaitech}"               # explicit profile for every AWS call
: "${AWS_REGION:=us-east-1}"
: "${GR_INSTANCE:=ghostreplay-prod}"
: "${GR_STATIC_IP:=ghostreplay-prod-ip}"
: "${GR_KEY_PAIR:=ghostreplay-prod-key}"
: "${GR_BUNDLE:=small_3_0}"                  # 2 GB RAM, 2 vCPU, 60 GB SSD, IPv4 — $12/month
: "${GR_BLUEPRINT:=ubuntu_24_04}"
: "${GR_AZ:=us-east-1a}"
: "${GR_DOMAIN:=ghostreplay.hayaix.tech}"
: "${GR_HOSTED_ZONE_ID:=Z0868301OHT2GP0EYYDO}"  # Route 53 zone for hayaix.tech
: "${GR_SSH_KEY:=$HOME/.ssh/ghostreplay-prod}"
: "${GR_SSH_USER:=ubuntu}"
# Source address allowed to SSH (besides the Lightsail browser console). Defaults to the
# public IPv4 address of the machine running the script.
: "${GR_ADMIN_CIDR:=}"

GR_TAGS=(key=Project,value=GhostReplay key=Environment,value=Production
         key=Purpose,value=Kiroween2026 key=Owner,value=Hayaix)

export AWS_PROFILE AWS_REGION
aws_ls() { aws --profile "$AWS_PROFILE" --region "$AWS_REGION" lightsail "$@"; }

gr_ip() {
  aws_ls get-static-ip --static-ip-name "$GR_STATIC_IP" --query staticIp.ipAddress --output text
}

gr_ssh() {
  ssh -i "$GR_SSH_KEY" -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new \
      -o ServerAliveInterval=30 "$GR_SSH_USER@$(gr_ip)" "$@"
}

gr_scp() {
  scp -i "$GR_SSH_KEY" -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new "$@"
}

log() { printf '\033[1;35m==>\033[0m %s\n' "$*" >&2; }
die() { printf '\033[1;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

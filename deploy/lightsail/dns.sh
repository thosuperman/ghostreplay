#!/usr/bin/env bash
# Point $GR_DOMAIN at the instance's static IP (Route 53 UPSERT of that one A record only).
#
#   deploy/lightsail/dns.sh
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
source "$here/config.sh"

ip=$(gr_ip)
[[ $ip =~ ^[0-9.]+$ ]] || die "no static IP found for $GR_STATIC_IP"
zone=$(aws --profile "$AWS_PROFILE" route53 get-hosted-zone --id "$GR_HOSTED_ZONE_ID" \
  --query HostedZone.Name --output text)
[[ "$GR_DOMAIN." == *".$zone" ]] || die "$GR_DOMAIN is not in hosted zone $zone"

change=$(cat <<EOF
{"Comment":"GhostReplay Lab (Kiroween 2026)","Changes":[{"Action":"UPSERT","ResourceRecordSet":{
 "Name":"$GR_DOMAIN.","Type":"A","TTL":300,"ResourceRecords":[{"Value":"$ip"}]}}]}
EOF
)
log "UPSERT A $GR_DOMAIN -> $ip (TTL 300) in $zone"
id=$(aws --profile "$AWS_PROFILE" route53 change-resource-record-sets \
  --hosted-zone-id "$GR_HOSTED_ZONE_ID" --change-batch "$change" --query ChangeInfo.Id --output text)
aws --profile "$AWS_PROFILE" route53 wait resource-record-sets-changed --id "$id"
log "Route 53 change $id is INSYNC"
for ns in $(aws --profile "$AWS_PROFILE" route53 get-hosted-zone --id "$GR_HOSTED_ZONE_ID" \
    --query 'DelegationSet.NameServers' --output text); do
  printf '  %-28s %s\n' "$ns" "$(dig +short A "$GR_DOMAIN" "@$ns" | tr '\n' ' ')"
done

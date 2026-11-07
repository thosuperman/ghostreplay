#!/usr/bin/env bash
# Delete everything provision.sh and dns.sh created: the DNS record, the static IP, the
# instance (and its disk) and the key pair. Asks for confirmation; download backups first.
#   deploy/lightsail/teardown.sh
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
source "$here/config.sh"
echo "This permanently deletes $GR_INSTANCE, $GR_STATIC_IP, $GR_KEY_PAIR and the A record"
echo "for $GR_DOMAIN in account profile $AWS_PROFILE ($AWS_REGION). Run backup.sh first."
read -r -p "Type the instance name to continue: " answer
[ "$answer" = "$GR_INSTANCE" ] || die "aborted"

ip=$(gr_ip 2>/dev/null || true)
current=$(aws --profile "$AWS_PROFILE" route53 list-resource-record-sets \
  --hosted-zone-id "$GR_HOSTED_ZONE_ID" --query \
  "ResourceRecordSets[?Name=='$GR_DOMAIN.' && Type=='A'].ResourceRecords[0].Value" --output text)
if [ -n "$current" ] && [ "$current" != None ]; then
  [ "$current" = "$ip" ] || die "A record points to $current, not $ip; remove it manually"
  aws --profile "$AWS_PROFILE" route53 change-resource-record-sets \
    --hosted-zone-id "$GR_HOSTED_ZONE_ID" --change-batch \
    "{\"Changes\":[{\"Action\":\"DELETE\",\"ResourceRecordSet\":{\"Name\":\"$GR_DOMAIN.\",\"Type\":\"A\",\"TTL\":300,\"ResourceRecords\":[{\"Value\":\"$current\"}]}}]}" >/dev/null
  log "deleted A record $GR_DOMAIN"
fi
aws_ls detach-static-ip --static-ip-name "$GR_STATIC_IP" >/dev/null 2>&1 || true
aws_ls release-static-ip --static-ip-name "$GR_STATIC_IP" >/dev/null 2>&1 && log "released $GR_STATIC_IP" || true
aws_ls delete-instance --instance-name "$GR_INSTANCE" >/dev/null && log "deleting $GR_INSTANCE"
aws_ls delete-key-pair --key-pair-name "$GR_KEY_PAIR" >/dev/null 2>&1 && log "deleted $GR_KEY_PAIR" || true
log "done; the local key $GR_SSH_KEY was kept"

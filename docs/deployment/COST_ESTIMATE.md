# Cost estimate

Prices are for `us-east-1` and in USD. The instance price was read from the Lightsail `GetBundles` API on 2026-11-07, just before provisioning.

| Item | Monthly cost | Notes |
|---|---|---|
| Lightsail instance `small_3_0` (2 GB RAM, 2 vCPU, 60 GB SSD, public IPv4) | **$12.00** | The approved bundle. The price covers the IPv4 address and 3 TB of outbound transfer. |
| Static IP `ghostreplay-prod-ip` | $0.00 | Free while attached to a running instance. A detached static IP is charged, which is why `teardown.sh` releases it. |
| Outbound data transfer | $0.00 | 3 TB included. A visitor session moves under 1 MB; the dashboard is about 100 KB compressed. |
| Route 53 | about $0.00 extra | The `hayaix.tech` hosted zone already existed and is billed with or without this record. One A record adds no fixed cost; queries cost $0.40 per million. |
| Let's Encrypt certificate | $0.00 | |
| Backups | $0.00 | Stored on the instance disk. Lightsail snapshots, at about $0.05 per GB-month, were not enabled because they weren't approved. |
| Monitoring | $0.00 | systemd timer and journal. No third-party service. |
| **Total added cost** | **about $12.00 per month** | Prorated hourly, so tearing down early costs less. |

## Things that would change the cost

| Change | Effect |
|---|---|
| Moving to a bigger bundle | Needs explicit approval. Measured use (about 100 MiB for both labs together under a burst, CPU mostly idle) gives no reason to. |
| Stopping the instance | Lightsail keeps charging for a stopped instance. Only deleting it stops the charge. |
| Lightsail snapshots | About $0.05 per GB-month of snapshot size. Not enabled. |
| Exceeding 3 TB per month of outbound transfer | $0.09 per GB over the allowance. Unrealistic for this demo. |

## Ending the cost after the hackathon

```bash
deploy/lightsail/backup.sh     # optional: download the data first
deploy/lightsail/teardown.sh   # deletes the A record, static IP, instance and key pair
```

Billing stops when the instance is deleted. Nothing else that costs money was created.

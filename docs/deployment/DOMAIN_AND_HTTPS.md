# Domain and HTTPS

## DNS

`hayaix.tech` is hosted in **Amazon Route 53**, in the same AWS account as the instance. The hosted zone is `Z0868301OHT2GP0EYYDO`, and the registrar delegates to the `awsdns` name servers.

The deployment added exactly one record:

```text
Type: A
Name: ghostreplay.hayaix.tech
Value: 34.226.55.219        (Lightsail static IP ghostreplay-prod-ip)
TTL: 300
```

`deploy/lightsail/dns.sh` creates it with a Route 53 `UPSERT` for that single name. Before writing, it checks that the domain belongs to the zone. Afterwards it waits for the change to reach `INSYNC` and queries all four authoritative name servers.

No other record was created or changed. `hayaix.tech`, `www`, `kiseki`, `freelanceflow`, the mail records and the CAA record are untouched. (A `freelanceflow.hayaix.tech` A record appeared in the zone during this deployment; it wasn't created by these scripts.)

### If DNS has to be set up by hand

Create the record above with the static IP that `deploy/lightsail/provision.sh` prints, or that this command returns:

```bash
aws --profile hayaitech --region us-east-1 lightsail get-static-ip \
  --static-ip-name ghostreplay-prod-ip --query staticIp.ipAddress --output text
```

## HTTPS

Caddy gets and renews the certificate automatically from Let's Encrypt, using the TLS-ALPN-01 challenge on port 443 (HTTP-01 on port 80 also works). The first certificate was issued on 2026-11-07 by `YE1` and is valid until 2027-02-05. Caddy renews it well before then. Certificates and the ACME account are stored in `/var/lib/caddy`.

- **CAA:** the `hayaix.tech` CAA record is `0 issue "letsencrypt.org"`, which allows only Let's Encrypt. That's the issuer Caddy uses. If it ever fell back to ZeroSSL, that issuance would be refused, so the CAA record must keep allowing Let's Encrypt.
- **Redirect:** plain-HTTP requests to the domain get `308 Permanent Redirect` to `https://`.
- **Unknown hosts:** requests for the bare IP or any other name on port 80 get 404.
- **HSTS:** `max-age=31536000`, without `includeSubDomains`, so other `hayaix.tech` subdomains are unaffected.
- **Protocols:** HTTP/2 over TCP and HTTP/3 over UDP 443.
- **Mixed content:** none. Every asset and API call is relative to the same origin, fonts are bundled, and nothing loads from a CDN.

## Checking from anywhere

```bash
dig +short ghostreplay.hayaix.tech
curl -sSI http://ghostreplay.hayaix.tech/ | head -3          # 308 → https
curl -sS https://ghostreplay.hayaix.tech/lab/support/api/health
echo | openssl s_client -connect ghostreplay.hayaix.tech:443 -servername ghostreplay.hayaix.tech 2>/dev/null \
  | openssl x509 -noout -issuer -dates
```

## Changing the domain

1. Point the new name at the static IP.
2. Change the site address in [`deploy/lightsail/Caddyfile`](../../deploy/lightsail/Caddyfile), or set `GHOSTREPLAY_DOMAIN` in Caddy's environment.
3. Change `GHOSTREPLAY_CORS_ORIGINS` in [`ghostreplay.env`](../../deploy/lightsail/ghostreplay.env) and `GR_DOMAIN` in `config.sh`.
4. Deploy. Caddy gets the new certificate on first use.

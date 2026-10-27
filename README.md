# IPGeolocation.io OpenAPI specs

Official OpenAPI 3.0 specifications for the [IPGeolocation.io](https://ipgeolocation.io) APIs, a real-time IP intelligence platform used by developers to build location-aware, secure, and personalized applications:

- **IP Geolocation API**: Lookup country, city, region, latitude, longitude, ISP, ASN, and company data for any IPv4 or IPv6 address or domain name.
- **IP Security API**: Detect VPNs, proxies, Tor nodes, threat scores, and attacker flags for fraud prevention and access control.
- **ASN API**: Retrieve Autonomous System Number details including organization, country, ASN type, RIR, routes, peers, upstreams, and downstreams for any IP address or ASN number.
- **IP Abuse Contact API**: Retrieve abuse contact information for any IPv4 or IPv6 address to report malicious activity and network abuse.
- **Timezone API**: Retrieve accurate timezone, UTC offset, and daylight saving data by IP address or location name.
- **Astronomy API**: Get sunrise, sunset, moon phase, and solar position data by geographic coordinates.
- **User-Agent API**: Parse browser, operating system, and device details from any user agent string.

All endpoints support JSON and XML responses and authenticate via API key. A free tier with up to 1,000 credits per day is available with no credit card required.

Full documentation: https://ipgeolocation.io/documentation.html
Get your free API key: https://app.ipgeolocation.io
Browse and try these APIs in Postman: https://www.postman.com/ipgeolocation-io/ipgeolocation-io-api-hub/overview

## Layout

Each API has its own directory with a real OpenAPI 3.0 document in both formats:

```
<api>/openapi.json
<api>/openapi.yaml
```

for `<api>` in `ip-location-api`, `ip-security-api`, `asn-api`, `ip-abuse-contact-api`, `timezone-api`, `user-agent-api`, `astronomy-api`.

At the repo root:

- **`openapi.yaml`** — a real, combined OpenAPI 3.0 document covering every API above in one file.
- **`openapi.json`** — **not an OpenAPI document.** It's a Postman v2.1 collection export with the same API coverage as `openapi.yaml`, kept here for convenience (e.g. importing straight into Postman). If you need the combined spec in JSON, convert `openapi.yaml`, or use the per-API `openapi.json` files, which are real OpenAPI JSON.

# SURAKSH Security

- JWT secrets and machine credentials are environment-configured.
- Browser DTOs contain no plaintext connector credentials.
- Machine ingestion requires `X-Edge-Key`; the configured value is a SHA-256 digest.
- Registry, detections, watchlists, and VMS reads are organization-scoped; administrative writes require server-side admin checks.
- CSV uploads are limited to 1 MB and 1,000 rows.
- All sample records are marked `is_demo` and user-facing screens show the synthetic-data notice.
- Government systems such as VAHAN, SARTHI, eGujCop, AFIS, and NAFIS are not connected. Official authorization and APIs are required before any future connector is enabled.

Remaining hardening before production: rotate the local Compose demo secret, add per-connector key records and revocation UI, add Redis-backed rate limiting, expand audit coverage to every new mutation, and run a PostGIS-backed security test suite.

# Security — starter limitations

**Do not expose the Docker development stack publicly or upload client-confidential exploration data.**

Implemented: Argon2, JWT with limited lifetime, per-organization API membership checks, tenant-keyed project queries, initial PostgreSQL RLS policies and a fixed external STAC URL.

Still pending: RLS integration tests with distinct runtime and migration database roles, signed organization-scoped object URLs, secure production cookie/session strategy, MFA, audit logs, rate limiting, token revocation, incident procedures, backup and restore testing, CSRF defenses and robust data retention policies.

The current frontend uses sessionStorage for access tokens for prototyping; a production deployment must replace this with a suitable hardened authentication model. No secrets or customer data should ever be committed to this repository.

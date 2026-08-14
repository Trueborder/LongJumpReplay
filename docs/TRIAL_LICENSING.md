# LongJumpReplay free trial

The customer installer contains a local 72-hour evaluation mode. On first
launch, the user chooses paid activation or starts the trial directly; no
email address, registration API, Cloudflare route, or always-on computer is
required. The trial allows the full capture/freeze/replay/judging workflow and
three successful final exports. After expiry or the export limit, paid
activation is required for further final exports; after expiry, the application
remains at activation.

## Optional service deployment (legacy)

`trial_service/app.py` remains available for deployments that need centrally
registered trials, but the desktop application no longer calls it by default.
Deploy it behind HTTPS at `https://api.tomaspisar.cz/longjumpreplay`, or set
`LJR_TRIAL_SERVICE_URL` in a custom build that uses the legacy registration
client.
The service requires:

- `LONGJUMP_TRIAL_KEY_PATH`: private RSA JSON key containing `n` and `d`;
- `LJR_TRIAL_DB_PATH`: durable private database path;
- HTTPS termination, rate limiting, backups, and an applicable retention policy.

The matching public key is embedded in `src/trial.py`. Never commit the
private key or trial database. Rotate keys by shipping a release that accepts
both old and new public keys during the transition.

The desktop client uses WorldTimeAPI for trusted UTC time. If it is
unavailable, the trial continues using the last trusted local deadline and
cannot be extended by moving the clock backward. This is intended to prevent
casual abuse, not to provide DRM-level protection.

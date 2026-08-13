# LongJumpReplay free trial

The customer installer contains a 72-hour evaluation mode. On first launch,
the user chooses paid activation or trial registration. The trial allows the
full capture/freeze/replay/judging workflow and three successful final
exports. After expiry or the export limit, paid activation is required for
further final exports; after expiry, the application remains at activation.

## Service deployment

`trial_service/app.py` is a dependency-free WSGI service. Deploy it behind
HTTPS at `https://api.tomaspisar.cz/longjumpreplay`, or set
`LJR_TRIAL_SERVICE_URL` in the customer build environment to another endpoint.
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

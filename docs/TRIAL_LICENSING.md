# LongJumpReplay free trial

The customer installer contains a local 72-hour evaluation mode. On first
launch, the user chooses paid activation or starts the trial directly; no
email address, registration API, Cloudflare route, or always-on computer is
required. The replay-only showcase allows camera capture, freeze, replay, saved
still frames, and three successful standalone video exports. Competition setup,
rosters, judging, verdicts, results, evidence packages, and competition package
exports are disabled.

The deadline is enforced locally from the machine-bound protected state. When
the 72 hours pass, all trial actions lock immediately and the application asks
the user to activate a paid licence or exit. The trial state is deliberately
non-resettable by the customer; removing the visible state file does not make
the same computer eligible again. Windows DPAPI is used when available, with
the existing protected-state fallback on other platforms.

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

Legacy signed service trials use WorldTimeAPI for trusted UTC time. Local
trials remain offline by design and cannot be extended by moving the clock
backward because the furthest-seen timestamp is persisted. This is intended to
prevent casual abuse, not to provide DRM-level protection.

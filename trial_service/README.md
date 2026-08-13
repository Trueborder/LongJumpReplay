# LongJumpReplay trial service

This is a small WSGI service for the free 72-hour evaluation. It is not
deployed by the desktop project automatically.

Production requirements:

- serve it behind HTTPS at the configured API hostname;
- set `LONGJUMP_TRIAL_KEY_PATH` to a private RSA JSON key containing `n` and
  `d` (never commit or distribute it);
- set `LJR_TRIAL_DB_PATH` to durable private storage;
- protect the service with rate limiting, backups, access logging policy, and
  the applicable privacy/retention policy.

The desktop client posts to `/v1/trials`. It uses WorldTimeAPI directly for
trusted UTC time after registration, and continues from its last trusted local
deadline when the time service is unavailable.

For local development:

```powershell
$env:LONGJUMP_TRIAL_KEY_PATH='C:\secure\LongJumpReplay-trial-private.json'
$env:LJR_TRIAL_DB_PATH='C:\secure\LongJumpReplay-trials.json'
python -m trial_service.app
```

The public verification key is fixed in `src/trial.py`; if the production key
is rotated, update that public key in a controlled release and keep old-key
verification during the transition.

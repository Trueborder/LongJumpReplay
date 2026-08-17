# LongJumpReplay license service

Issues a licence automatically when a Stripe purchase completes and emails it to
the customer.

The customer installs LongJumpReplay, starts the 72-hour trial, and copies the
machine code from the activation window. They paste it into a custom field at
Stripe checkout. Stripe then calls this service, which signs a licence bound to
that machine code and emails it. The customer pastes the key back into the
activation window.

## Why this service has its own signing key

It signs with a **different** key from `tools/.license_private_key.json`. The
offline owner key never goes near the internet. The app trusts both:
`src/licensing.py` checks `PUBLIC_KEY_N` first, then `SERVICE_PUBLIC_KEY_N`.

If this server is ever compromised, rotate `SERVICE_PUBLIC_KEY_N` and ship a
release. Licences signed offline keep working, and you can still issue licences
by hand while the service is down.

## Configuration

Required:

| Variable | Meaning |
| --- | --- |
| `LONGJUMP_SERVICE_KEY_PATH` | Private RSA JSON key (`{"n", "d"}`). Never commit. |
| `STRIPE_WEBHOOK_SECRET` | Endpoint signing secret, starts with `whsec_`. |
| `LJR_SMTP_HOST` | Outbound mail host. |
| `LJR_SMTP_USER` / `LJR_SMTP_PASSWORD` | Mail credentials. |
| `LJR_MAIL_FROM` | Sender address the customer sees. |

Optional:

| Variable | Default | Meaning |
| --- | --- | --- |
| `LJR_LICENSE_DB_PATH` | `license_service/data.json` | Order store. Put it on durable storage. |
| `LJR_MACHINE_FIELD_KEY` | `machine_code` | Stripe custom field key. |
| `LJR_SMTP_PORT` | `587` | SMTP port (STARTTLS). |
| `LJR_OWNER_EMAIL` | unset | Notified when an order needs manual attention. |

Set `LJR_OWNER_EMAIL`. Without it, an order that cannot be fulfilled is recorded
but nobody is told.

## Generating the service key

```powershell
py -3.12 tools\generate_signing_key.py tools\.license_service_private_key.json
```

Copy the printed modulus into `SERVICE_PUBLIC_KEY_N` in `src/licensing.py`, ship
a release built from that source, then move the private key file to the server.
Back it up first: losing it means rotating the key and shipping again.

## Stripe setup

1. Create a **Payment Link** for LongJumpReplay (Payment Links support custom
   fields; the embedded pricing table does not).
2. Under **Options** choose **Add custom fields** and add a **Text** field:
   - key `machine_code` (must match `LJR_MACHINE_FIELD_KEY`)
   - label `Machine code (shown in the app)`
   - mark it **required**
3. Point the website Buy buttons at that payment link.
4. In Workbench → **Webhooks**, create an event destination for
   `checkout.session.completed` pointing at
   `https://<your-host>/v1/stripe/webhook`.
5. Copy the endpoint signing secret into `STRIPE_WEBHOOK_SECRET`.

Custom field labels are not translated. Use the `locale` URL parameter on the
payment link if you want the checkout page to match the label language.

## Running it

```powershell
$env:LONGJUMP_SERVICE_KEY_PATH='C:\secure\LongJumpReplay-service-key.json'
$env:STRIPE_WEBHOOK_SECRET='whsec_...'
$env:LJR_SMTP_HOST='smtp.example.com'
$env:LJR_MAIL_FROM='info@tomaspisar.cz'
python -m license_service.app
```

Serve it behind HTTPS with a real certificate. Stripe requires TLS 1.2+, will not
follow redirects, and only delivers to publicly reachable HTTPS URLs.

Test locally without spending money:

```bash
stripe listen --forward-to localhost:8081/v1/stripe/webhook
stripe trigger checkout.session.completed
```

Use the signing secret `stripe listen` prints, not the Dashboard one.

## Behaviour worth knowing

- **Signatures are verified manually** in `stripe_signature.py`, following
  Stripe's documented scheme: HMAC-SHA256 over `timestamp.body`, only the `v1`
  scheme trusted, constant-time comparison, 5-minute replay window. Forged,
  unsigned, tampered, and stale requests are all rejected with 400 and issue
  nothing. There are tests for each of those.
- **Duplicate deliveries issue one licence.** Stripe retries until it gets a
  2xx, so processed event IDs are recorded and replays return `200 {"duplicate"}`.
- **Business problems return 200, not an error.** A malformed or missing machine
  code is recorded as `needs_attention` and mailed to `LJR_OWNER_EMAIL`.
  Returning an error would make Stripe retry a request that can never succeed.
  Genuine outages return 503 so Stripe *does* retry.
- **Orders are recorded before the email is attempted**, so a mail failure never
  loses a paid order. Re-issue those by hand with the license generator.
- Fulfilment happens synchronously. That is fine at this volume; if orders ever
  arrive in bursts, move it to a queue and return 200 first.

## Operational notes

The order store contains customer names, email addresses, and machine codes.
Keep it on private storage, back it up, and apply the same retention policy as
the rest of the site. `data.json` is gitignored.

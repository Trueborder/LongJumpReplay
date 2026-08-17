# Website licensing copy and backend integration

## Status: the website describes a system that is not built

`website/tomaspisar.cz` describes email-based activation, a two-computer device
limit, periodic online verification, a 30-day offline grace period, and a
12-month updates and support period. **None of this is implemented.** As of the
current release:

| Website says | Application actually does |
| --- | --- |
| Email-based activation, verification code | Paste an `LJR2…` key. `src/licensing.py` never asks for, sends or validates an email |
| Up to 2 activated computers | Exactly 1. No seat count or activation registry exists |
| Periodic online verification | `src/licensing.py` imports no networking. Verified once, at startup, offline |
| Offline for up to 30 days | No online check exists, so offline use is unlimited |
| Updates and support for 12 months | Nothing records when a customer bought |
| Deactivate a computer, activate another | No deactivation exists. Moving machines means a new key issued by hand |
| License status Active/Inactive/Expired/Suspended | No status field exists. An issued key cannot be revoked |

A buyer paying today receives a manually issued key locked to one computer,
which works offline forever. Close this gap before the copy is deployed, or
treat the deployed site as a description of the intended product rather than
the shipped one.

## Where the numbers live

All customer-visible licensing figures come from `licensing` in
`website/tomaspisar.cz/site.config.js`:

```js
licensing: { deviceLimit: 2, offlineGraceDays: 30, updateMonths: 12 }
```

`script.js` writes them into `[data-license-devices]`, `[data-license-grace]`
and `[data-license-updates]`. Changing a number there changes every page at
once. Keep these in step with whatever the backend actually enforces — they are
presented to customers as commitments.

Because those handlers set `textContent`, an element must never carry both a
`data-license-*` attribute and `data-en`/`data-cs`: the translation pass runs
last and would overwrite the injected number. Use a nested element, as the
existing pages do:

```html
<span>Up to <b data-license-devices>2</b> <span data-en="computers" data-cs="počítače">computers</span></span>
```

## Intended architecture

```
Stripe Checkout -> Stripe webhook -> Cloudflare Worker -> Cloudflare D1
                                                           ├── Customers
                                                           ├── Licenses
                                                           └── Device activations

LongJumpReplay -> Cloudflare Worker API -> license verification
                                        -> signed authorization
                                        -> local/offline authorization
```

Nothing in this repo implements the Worker or D1. `license_service/` is a
different design: a WSGI service that signs a machine-bound key after a Stripe
`checkout.session.completed` webhook and emails it. It has no device registry,
no email verification, no status field and no deactivation, so it does not
satisfy the model the website describes.

## Where the frontend would connect

The website is static and calls no API today, which is deliberate — no fake
endpoints were added. When the backend exists:

- **Purchase**: unchanged. Stripe already collects the email address the
  licence is created against. Point the webhook at the Worker.
- **Activation, verification, device add/remove**: these happen in the desktop
  application, not on the website. The site only explains them.
- **Device management page**: no UI exists and none was stubbed. `/licensing/`
  currently tells customers to email for a slot to be freed. If a self-service
  page is built, replace that sentence and link to it from `#devices`.

## What the application needs before the copy is true

1. Email verification: request a code for a purchased address, and verify it.
2. A device registry keyed by licence, enforcing `deviceLimit`, with an
   explicit deactivate.
3. A periodic verification call that refreshes a signed local authorization,
   plus expiry of that authorization after `offlineGraceDays`, with a clear
   in-app prompt rather than a silent failure.
4. A licence status the server can set, and that the app honours.
5. An updates entitlement recorded per customer, if the 12-month claim is to
   mean anything technically rather than as a goodwill promise.

Until 1–3 exist, the app cannot behave as described no matter what the backend
does, because `src/licensing.py` has no network path at all.

## Also outstanding

There is still no Terms of Service or refund policy on the site, while it takes
live card payments from EU consumers. Missing: seller identification (name,
address, IČO, VAT status), delivery timing, the 14-day right of withdrawal, and
the ČOI as the out-of-court dispute body. `privacy/index.html` now describes
server-side storage of email addresses and device activations, which is a
processing description that should be reviewed once the backend is real.

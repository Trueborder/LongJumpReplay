# Website licensing copy and backend integration

## Status: the licensing system is deployed

`website/tomaspisar.cz` describes email-based activation, a two-computer device
limit, periodic online verification, a 30-day offline grace period, and a
12-month updates and support period. The activation, device and verification
claims are now implemented by the deployed Worker and 3.2 desktop client:

| Website says | Current implementation |
| --- | --- |
| Email-based activation, verification code | Worker OTP flow creates a one-use activation grant |
| Up to 2 activated computers | D1 device registry enforces two active seats |
| Periodic online verification | The client refreshes a signed authorization every 30 days |
| Offline for up to 30 days | The client works offline until its authorization expires |
| Deactivate a computer, activate another | Desktop activation and the customer portal can deactivate a device |
| License status Active/Inactive/Expired/Suspended | Stripe webhooks synchronize status and verification honours it |
| Updates and support for 12 months | Still a release/support policy, not a D1 entitlement field |

A full Stripe test-mode purchase rehearsal remains a release validation gate;
the production endpoint and live webhook are already deployed.

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

`licensing-api/` implements the Worker/D1 design. `license_service/` is a
different, legacy WSGI service that signs a machine-bound key after a Stripe
`checkout.session.completed` webhook and emails it; it is not used by the new
purchase or activation flow.

## Where the frontend would connect

The marketing website remains static. The separate customer portal at
`account.tomaspisar.cz` lets any email address authenticate by OTP. Before a
purchase it shows an empty account with a purchase link; a licence bought with
the same normalized address appears automatically:

- **Purchase**: unchanged. Stripe already collects the email address the
  licence is created against. Point the webhook at the Worker.
- **Activation and periodic verification**: these happen in the desktop
  application.
- **Account management**: the portal lists licence status, invoices and
  activated computers, can deactivate a device, and opens Stripe Customer
  Portal for billing management.

## Implemented application contract

1. Email verification creates a one-use activation grant.
2. The Worker enforces the two-device registry and supports deactivation.
3. The desktop refreshes a signed authorization periodically and fails clearly
   when its 30-day offline window is exhausted.
4. Server licence status and subscription grace are enforced at refresh time.
5. The customer portal provides billing and device self-service; update
   entitlement remains a separate release-policy decision.

## Also outstanding

The technical licensing flow is now implemented: Stripe creates the licence,
the customer activates by email, and `account.tomaspisar.cz` provides OTP
login, device management, invoices and Stripe billing management. The legal
release gate remains separate: publishable Terms, seller identification
(name, address, IČO, VAT status), delivery timing, the 14-day withdrawal and
refund information, and the ČOI out-of-court dispute body must be supplied and
reviewed before treating the public checkout as legally complete.
`privacy/index.html` describes server-side storage of email addresses and
device activations and should receive the same final review.

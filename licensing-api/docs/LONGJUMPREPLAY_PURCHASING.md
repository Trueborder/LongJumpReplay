# LongJumpReplay purchasing and licence lifecycle

This document covers LongJumpReplay only. EconomySuite uses a separate Worker module and D1 database.

## Checkout

`GET /api/longjumpreplay/catalog` reads the two configured LongJumpReplay Stripe prices and returns safe public catalogue data. It never returns the Stripe secret. `POST /api/longjumpreplay/checkout` accepts an email, configured price ID, client idempotency key, and three explicit confirmations: purchase terms, immediate activation, and withdrawal-rights acknowledgement. The Worker re-reads the Stripe price and stores the displayed price, currency, product, policy versions, timestamps, consent IP and user-agent context before creating a Checkout Session.

The browser is never authoritative for price, tax treatment, entitlement, or consent evidence. The Checkout Session carries only safe references: internal order ID, product, licence type, and policy versions.

## Order states

`checkout_pending` → `paid` → entitlement `active` and delivery `delivered`. Payment failures remain attached to the order. Refunds and disputes update the order to `partially_refunded`, `refunded`, `disputed`, `dispute_won`, or `dispute_lost`; entitlement effects remain auditable and are not silently inferred from a browser return page.

The `ljr_orders` row stores confirmation status, receipt reference, Stripe identifiers, policy versions, and delivery status. The portal exposes safe order fields in billing and the data export. Sensitive consent context is retained server-side and is not exposed in the portal order summary.

## Webhooks and retries

Stripe signatures are verified before processing. `stripe_events` records `processing`, `processed`, or `failed`. A completed event is ignored on redelivery; a failed event can be retried. Licence creation is guarded by the order licence ID and the existing subscription uniqueness constraint. Confirmation email failure is visible as `confirmation_status=failed` and must be handled through support or a future resend operator action.

## Existing licence rules

The current configuration remains authoritative: two devices by default, up to 30 days between offline checks, seven subscription grace days, lifetime licences without subscription expiry, and subscription licences active while the configured Stripe subscription is active or within the configured grace behaviour. Do not change these values in legal copy or Stripe without updating the configuration and policy review.

## Deployment configuration

Required production secrets remain existing Worker secrets: `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `MAIL_API_KEY`, `VERIFICATION_PEPPER`, `AUTHORIZATION_PRIVATE_KEY`, and optional activation-key encryption/Turnstile secrets. Apply the LJR D1 migrations through the existing deployment process. Add the Stripe webhook event types for checkout completion, async payment failure, subscription changes, refunds, and disputes; verify the endpoint in Stripe Dashboard before enabling production sales.

No secret values belong in this document, the website bundle, browser responses, or committed environment files.

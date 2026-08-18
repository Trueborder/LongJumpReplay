# Website cookie and session report

Last verified in production: 19 August 2026.

## Current design

The public website and account portal do not use analytics or advertising
cookies. Visitors can accept or decline optional preference cookies, and can
reopen the same choice from **Cookie settings** in every footer.

Declining removes the theme and language preferences. Accepting stores the
current theme and language. Until a choice is accepted, those preferences are
kept only for the current page session and are not persisted.

The account portal uses a separate essential authentication cookie after a
visitor proves control of an email address with a six-digit code. Portal access
does not require a purchased licence; an authenticated customer without a
licence sees the no-licence state and a purchase link.

## Cookies

| Name | Purpose | Lifetime | Security |
| --- | --- | --- | --- |
| `ljr-consent` | Remembers accepted or declined preference-cookie choice | 180 days | `Secure`, `SameSite=Lax` |
| `site-theme` | Optional light/dark preference | 1 year | Written only after consent; `Secure`, `SameSite=Lax` |
| `site-language` | Optional English/Czech preference | 1 year | Written only after consent; `Secure`, `SameSite=Lax` |
| `ljr-portal-session` | Essential account authentication | 30 days | `HttpOnly`, `Secure`, `SameSite=Lax`, domain `.tomaspisar.cz`; server-side revocation on logout |

Stripe may set its own strictly necessary payment and fraud-prevention cookies
when the embedded pricing or Checkout interface is used. Stripe controls their
retention and security behavior.

## Production acceptance evidence

- Fresh mobile visit displayed the consent banner without horizontal overflow.
- Decline left only `ljr-consent=declined` and no preference cookies.
- Cookie settings reopened the banner and moved keyboard focus to Decline.
- Accept stored the consent, theme, and language cookies.
- The public and account sites expose the same footer settings control.
- Light-mode primary and outline buttons rendered with readable foreground and
  background colors and 48-pixel targets.
- The Stripe pricing element loaded and rendered; no paid transaction was made
  during acceptance testing.
- A synthetic unlicensed email completed request-code, verify-code, two
  authenticated account reads, and logout against production. The session was
  `HttpOnly`, `Secure`, `SameSite=Lax`, valid for 30 days, and rejected after
  logout. All synthetic customer, code, session, and email rate-limit rows were
  deleted after the test.

## Privacy disclosure

The bilingual privacy page documents all four first-party cookies, the account
session lifecycle, Stripe's necessary cookies, the absence of analytics and
advertising cookies, and the footer control for changing a decision later.

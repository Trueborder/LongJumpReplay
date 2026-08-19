# Long Jump Replay 3.2 — Changelog

## Licensing and customer account

- Added email-based customer activation through the deployed licensing API.
- Added a dedicated passwordless login at `https://account.tomaspisar.cz/login`
  and an authenticated dashboard at `https://account.tomaspisar.cz/dashboard`.
- Anyone can sign in by email before purchasing; unlicensed accounts show a
  direct purchase prompt and populate automatically after a matching purchase.
- Customers can view licence status, activated computers, invoices, and billing management.
- Customers can deactivate an activated computer from the portal.
- Added dashboard categories for licence timing, available computer slots,
  online-verification dates, downloads, billing, support, and session security.
- Added a Licence & account page to the desktop Settings dialog.
- The frozen app now verifies the device and plan at every startup and displays
  the result in the splash progress bar. A valid signed authorization preserves
  offline event use when the server is temporarily unreachable.
- Added the 30-day authorization refresh and 7-day subscription grace period to the release documentation.
- Added explicit Back and Activate controls to the desktop email-code step,
  including predictable focus restoration when returning to the email field.
- Device cards now show activation time as well as date. Verification messages
  use branded HTML with distinct app-activation and portal-login purpose labels
  and retain a complete plain-text fallback.

## Release

- Updated the product version to 3.2.
- The 3.2 installer must be built and validated on Windows before distribution.

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

## Release

- Updated the product version to 3.2.
- The 3.2 installer must be built and validated on Windows before distribution.

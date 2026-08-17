# LongJumpReplay license administration

Use `scripts\run\RUN_LICENSE_GENERATOR.bat` on the owner/support computer. The script
checks for `tools/.license_private_key.json` before opening the generator. Enter the
machine code supplied by the customer, their name, and an internal license ID.
Press **Generate key**, then use **Copy key** or **Save key…**.

Both `scripts\run\RUN_LICENSE_GENERATOR.bat` and
`scripts\build\BUILD_LICENSE_GENERATOR.bat` keep the console window open when they
finish, so a missing key or a build error stays readable when the script is
double-clicked from Explorer. Set `LONGJUMP_NO_PAUSE=1` to skip that pause when
calling them from another script.

Send only the generated `LJR2...` key to the customer. They paste it into the
activation dialog in LongJumpReplay. The key is bound to that machine code.

## Automatic issuing after a Stripe purchase

`license_service/` issues licences automatically when a Stripe payment
completes: the customer pastes their machine code into a custom field at
checkout, and the service emails them a signed key. See
`license_service/README.md` for Stripe and deployment setup.

That service signs with its own key, not the offline key described above. The
app accepts both (`PUBLIC_KEY_N` and `SERVICE_PUBLIC_KEY_N` in
`src/licensing.py`), so the offline key stays off the internet and either key
can be rotated without invalidating licences signed by the other. Manual issuing
with the generator keeps working regardless, and is the fallback whenever an
order is flagged `needs_attention`.

Keep `tools/.license_private_key.json` private and backed up securely. Never
include the license generator or the private-key file in a customer installer
or customer ZIP. If the admin EXE is moved outside the repository, set
`LONGJUMP_LICENSE_KEY_PATH` to the private-key file before launching it.
Losing the private key means previously issued licenses can still be verified,
but new licenses cannot be issued.

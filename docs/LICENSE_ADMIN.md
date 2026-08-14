# LongJumpReplay license administration

Use `scripts\run\RUN_LICENSE_GENERATOR.bat` on the owner/support computer. The script
checks for `tools/.license_private_key.json` before opening the generator. Enter the
machine code supplied by the customer, their name, and an internal license ID.
Press **Generate key**, then use **Copy key** or **Save key…**.

Send only the generated `LJR2...` key to the customer. They paste it into the
activation dialog in LongJumpReplay. The key is bound to that machine code.

Keep `tools/.license_private_key.json` private and backed up securely. Never
include the license generator or the private-key file in a customer installer
or customer ZIP. If the admin EXE is moved outside the repository, set
`LONGJUMP_LICENSE_KEY_PATH` to the private-key file before launching it.
Losing the private key means previously issued licenses can still be verified,
but new licenses cannot be issued.

# Windows installer trust

LongJumpReplay currently makes no code-signing change. There is no free,
publicly trusted certificate for a private commercial EXE that reliably removes
Microsoft Defender SmartScreen and browser reputation warnings.

The practical route for direct downloads is an Authenticode code-signing
certificate from a public certificate authority, signing both the Inno Setup
installer and the shipped EXE with SHA-256 plus an RFC 3161 timestamp. An EV
certificate may build reputation faster but is more expensive. An ordinary OV
certificate is usually the sensible starting point; warnings can still appear
until reputation develops. HTTPS, checksums and the existing signed update
manifest protect transport and update integrity, but they do not replace
Authenticode publisher identity.

When a certificate is purchased, add signing through secret-backed CI or a
hardware-backed signing service. Never commit a PFX, password, private key or
cloud-signing credential. Verify the final installer with `signtool verify /pa
/v` and test download plus launch on a clean Windows machine before release.

# Releasing LongJumpReplay

The desktop version has one source of truth: `src/__init__.py`. The Windows
file metadata, installer filename, portable archive name, website label and
signed update manifest all derive from it.

## One-time setup

1. Install Python 3.12 x64 and Inno Setup 6.
2. Run `scripts\setup\INSTALL_WINDOWS.bat`.
3. Keep `packaging\.update-signing-private.pem` only on the release computer.
   Back it up offline. It is ignored by Git and is never included in customer
   files. The matching public key in `src\update_public_key.py` is safe to
   commit and is embedded in the application.
4. Authenticate Wrangler for the Cloudflare account that owns the
   `longjumpreplay` R2 bucket.

If the update private key is lost, existing applications cannot trust newly
published manifests. Rotating it requires shipping an application containing
the new public key through another trusted distribution path.

## Prepare a release

1. Set the new semantic version in `src/__init__.py`.
2. Add the customer-visible changes to `CHANGELOG.md`.
3. Run `scripts\build\BUILD_INSTALLER.bat --no-pause`.
4. Test a clean install and an upgrade from the previous public installer.
5. Confirm that settings and activation under
   `%LOCALAPPDATA%\LongJumpReplay` survive the upgrade.

The build runs the complete non-GUI and isolated GUI suites, source and frozen
self-tests, builds the portable payload, and compiles
`release\LongJumpReplay-Setup-<version>.exe` with Inno Setup. The installer
keeps the original 3.1 AppId, so it upgrades the existing Program Files
installation instead of creating a second product.

## Publish

Run:

```text
scripts\release\PUBLISH_RELEASE.bat
```

After a successful build, the publisher signs and verifies the update
manifest, uploads immutable versioned objects, verifies their downloaded
hashes, replaces the stable installer alias, and uploads `latest.json` last:

```text
releases/<version>/LongJumpReplay-Setup-<version>.exe
releases/<version>/manifest.json
LJR_setup.exe
latest.json
```

Uploading the manifest last is the release boundary: customers cannot discover
an installer until its versioned object has already been uploaded and checked.
Use `scripts\release\PUBLISH_RELEASE.bat -SkipBuild` only when the exact local
installer has already passed the full release build in the same working tree.

The application checks `https://files.tomaspisar.cz/latest.json` during the
splash without delaying startup. A valid newer release offers Install, Skip
this version, and Ask later. The installer is accepted only when the manifest
signature, product/channel fields, HTTPS path, byte length and SHA-256 digest
all match.

## Roll back discovery

To point the stable channel back to an already archived release:

```text
scripts\release\ROLLBACK_RELEASE.bat 3.3.0
```

The rollback command downloads and verifies the archived installer and signed
manifest before replacing `LJR_setup.exe` and `latest.json`. Archived versioned
objects remain immutable. A rollback does not uninstall a version that a
customer already installed.

## Signing

The installer is not Authenticode-signed until a Windows code-signing
certificate is configured. The signed update manifest protects updater
integrity, but it does not replace Windows publisher reputation or SmartScreen
trust. Add Authenticode signing before wider public distribution.

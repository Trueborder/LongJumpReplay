/**
 * Sign a sample authorization with the Worker's exact signing code, so the
 * Python verifier can be checked against it. This is the riskiest seam in the
 * system: WebCrypto RSASSA-PKCS1-v1_5 on one side, a hand-rolled
 * pow(sig, e, n) verifier on the other, plus two independent JSON
 * canonicalisations that must agree byte for byte.
 *
 *   node scripts/interop-sign.mjs <private-key-pem-file> <out.json>
 */
import { readFileSync, writeFileSync } from "node:fs";

// Node 24 exposes WebCrypto, btoa and atob globally, so the Worker module runs
// here unmodified - which is the point: this tests the real signing code.
// Bundled from src/crypto.ts by esbuild so this exercises the real Worker code
// rather than a reimplementation:
//   npx esbuild src/crypto.ts --bundle --format=esm --platform=neutral --outfile=.interop-crypto.mjs
const { signAuthorization, canonicalPayload } = await import("../.interop-crypto.mjs");

const pemFile = process.argv[2];
const outFile = process.argv[3];

const raw = readFileSync(pemFile, "utf8");
const match = raw.match(/-----BEGIN PRIVATE KEY-----[\s\S]*?-----END PRIVATE KEY-----/);
if (!match) throw new Error("no PKCS#8 private key found in " + pemFile);
const pem = match[0];

const modulusMatch = raw.match(/=== public modulus[^\n]*\n(\d+)/);
if (!modulusMatch) throw new Error("no public modulus found in " + pemFile);

const claims = {
  licenseId: "lic_interop_test",
  licenseType: "lifetime",
  machineId: "Zm9vYmFyYmF6cXV4MTIzNDU2Nzg5MA",
  issuedAt: 1755400000,
  expiresAt: 1755400000 + 30 * 86400,
  maxDevices: 2,
};

const token = await signAuthorization(pem, claims);

// Canonicalisation of a payload containing non-ASCII and awkward characters,
// to prove the JS and Python encoders agree beyond the happy path.
const tricky = { b: "ěšč", a: 1, "c/d": "x\"y", e: null, f: true };

writeFileSync(
  outFile,
  JSON.stringify(
    {
      token,
      modulus: modulusMatch[1],
      claims,
      canonical_sample: canonicalPayload(tricky),
      canonical_input: tricky,
    },
    null,
    2,
  ),
);
console.log("wrote", outFile);
console.log("token prefix:", token.slice(0, 24) + "...");

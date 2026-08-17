/**
 * Generate the authorization signing keypair.
 *
 * The private half becomes the AUTHORIZATION_PRIVATE_KEY Worker secret and must
 * never leave the server. The printed modulus is the public half, embedded in
 * the desktop application so it can verify authorizations offline.
 *
 *   node scripts/generate-signing-key.mjs > key.txt
 *
 * Treat key.txt as a secret and delete it once the value is in `wrangler secret put`.
 */
import { generateKeyPairSync } from "node:crypto";

const { privateKey, publicKey } = generateKeyPairSync("rsa", {
  modulusLength: 2048,
  publicExponent: 65537,
});

const pkcs8 = privateKey.export({ type: "pkcs8", format: "pem" }).toString();
const jwk = publicKey.export({ format: "jwk" });

// JWK gives base64url big-endian; convert to the decimal integer the Python
// verifier expects for PUBLIC_KEY_N-style constants.
const modulus = BigInt("0x" + Buffer.from(jwk.n, "base64url").toString("hex"));
const exponent = BigInt("0x" + Buffer.from(jwk.e, "base64url").toString("hex"));

console.log("=== AUTHORIZATION_PRIVATE_KEY (secret - wrangler secret put) ===");
console.log(pkcs8.trim());
console.log();
console.log("=== public modulus for src/licensing.py (not secret) ===");
console.log(modulus.toString());
console.log();
console.log("public exponent:", exponent.toString());
console.log("modulus bits:", modulus.toString(2).length);

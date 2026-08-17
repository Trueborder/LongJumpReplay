/**
 * Build .dev.vars for local testing from a generated key file.
 * .dev.vars is gitignored; these values are for miniflare only and must never
 * be reused in production.
 *
 *   node scripts/make-dev-vars.mjs key.txt
 */
import { readFileSync, writeFileSync } from "node:fs";
import { randomBytes } from "node:crypto";

const raw = readFileSync(process.argv[2] ?? "key.txt", "utf8");
const pem = raw.match(/-----BEGIN PRIVATE KEY-----[\s\S]*?-----END PRIVATE KEY-----/)?.[0];
if (!pem) throw new Error("no PKCS#8 private key found");

// importPrivateKey strips headers and whitespace, so a single-line base64 body
// is accepted - which keeps .dev.vars to one line per value.
const oneLine = pem
  .replace(/-----BEGIN PRIVATE KEY-----/, "")
  .replace(/-----END PRIVATE KEY-----/, "")
  .replace(/\s+/g, "");

const lines = [
  "# Local development only. Gitignored. Do not reuse these in production.",
  `STRIPE_WEBHOOK_SECRET=whsec_local_test_secret`,
  `STRIPE_SECRET_KEY=`,
  `VERIFICATION_PEPPER=${randomBytes(32).toString("base64url")}`,
  `AUTHORIZATION_PRIVATE_KEY=${oneLine}`,
  `MAIL_API_KEY=`,
  "",
];
writeFileSync(".dev.vars", lines.join("\n"));
console.log("wrote .dev.vars (gitignored)");
console.log("STRIPE_WEBHOOK_SECRET = whsec_local_test_secret");
console.log("MAIL_API_KEY left empty: sending will fail loudly, which the tests rely on");

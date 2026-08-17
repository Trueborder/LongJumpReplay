/**
 * Signing and hashing.
 *
 * The authorization token is signed with RSASSA-PKCS1-v1_5 / SHA-256, which is
 * byte-compatible with the verifier already shipping in the desktop app
 * (`_rsa_verify_with_key` in src/licensing.py performs `pow(sig, e, n)` and
 * compares against an EMSA-PKCS1-v1_5 encoded digest). That lets the EXE verify
 * offline with no new dependencies, and keeps the private key on the server.
 */

import { AUTHORIZATION_PREFIX, AUTHORIZATION_VERSION, PRODUCT_ID } from "./config";
import type { LicenseType } from "./config";

const encoder = new TextEncoder();

export function base64UrlEncode(bytes: ArrayBuffer | Uint8Array): string {
  const view = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  let binary = "";
  for (const byte of view) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function base64ToBytes(value: string): Uint8Array {
  const binary = atob(value.replace(/-/g, "+").replace(/_/g, "/"));
  const out = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) out[i] = binary.charCodeAt(i);
  return out;
}

/**
 * Must match `canonical_payload` in src/licensing.py exactly:
 * sorted keys, no whitespace, non-ASCII left unescaped. A single byte of
 * difference makes every signature fail to verify.
 */
export function canonicalPayload(payload: Record<string, unknown>): string {
  const keys = Object.keys(payload).sort();
  const parts = keys.map((key) => `${JSON.stringify(key)}:${JSON.stringify(payload[key])}`);
  return `{${parts.join(",")}}`;
}

async function importPrivateKey(pem: string): Promise<CryptoKey> {
  const body = pem
    .replace(/-----BEGIN PRIVATE KEY-----/, "")
    .replace(/-----END PRIVATE KEY-----/, "")
    .replace(/\s+/g, "");
  if (!body) throw new Error("AUTHORIZATION_PRIVATE_KEY is empty");
  return crypto.subtle.importKey(
    "pkcs8",
    base64ToBytes(body),
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
    false,
    ["sign"],
  );
}

export interface AuthorizationClaims {
  licenseId: string;
  licenseType: LicenseType;
  machineId: string;
  issuedAt: number;
  expiresAt: number;
  maxDevices: number;
}

/**
 * Produce `LJRA1.<payload>.<signature>`, both parts base64url without padding -
 * the same shape as the existing LJR2 licence keys, so the client can reuse its
 * decoder.
 */
export async function signAuthorization(privateKeyPem: string, claims: AuthorizationClaims): Promise<string> {
  const payload = {
    product: PRODUCT_ID,
    version: AUTHORIZATION_VERSION,
    license_id: claims.licenseId,
    license_type: claims.licenseType,
    machine_id: claims.machineId,
    max_devices: claims.maxDevices,
    issued_at: claims.issuedAt,
    expires_at: claims.expiresAt,
  };
  const message = canonicalPayload(payload);
  const key = await importPrivateKey(privateKeyPem);
  const signature = await crypto.subtle.sign("RSASSA-PKCS1-v1_5", key, encoder.encode(message));
  return `${AUTHORIZATION_PREFIX}.${base64UrlEncode(encoder.encode(message))}.${base64UrlEncode(signature)}`;
}

/**
 * HMAC rather than a bare hash: a six-digit code has ~20 bits of entropy and
 * would fall to an offline brute force in milliseconds if the database leaked.
 * The pepper is a Worker secret, so a database leak alone is not enough.
 */
export async function hashCode(pepper: string, code: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(pepper),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const mac = await crypto.subtle.sign("HMAC", key, encoder.encode(code));
  return base64UrlEncode(mac);
}

/** Six digits, uniformly distributed - rejection sampling avoids modulo bias. */
export function generateVerificationCode(): string {
  const buffer = new Uint32Array(1);
  let value: number;
  do {
    crypto.getRandomValues(buffer);
    value = buffer[0];
  } while (value >= 4_294_000_000);
  return String(value % 1_000_000).padStart(6, "0");
}

export function generateToken(): string {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  return base64UrlEncode(bytes);
}

export async function sha256(value: string): Promise<string> {
  return base64UrlEncode(await crypto.subtle.digest("SHA-256", encoder.encode(value)));
}

export function randomId(prefix: string): string {
  return `${prefix}_${crypto.randomUUID().replace(/-/g, "")}`;
}

/** Length-independent comparison, so a mismatch reveals nothing through timing. */
export function timingSafeEqual(a: string, b: string): boolean {
  const left = encoder.encode(a);
  const right = encoder.encode(b);
  let diff = left.length ^ right.length;
  const length = Math.max(left.length, right.length);
  for (let i = 0; i < length; i += 1) {
    diff |= (left[i] ?? 0) ^ (right[i] ?? 0);
  }
  return diff === 0;
}

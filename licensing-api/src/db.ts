/**
 * All D1 access. Every query is parameterised - no string interpolation of
 * user-supplied values anywhere in this file.
 */

import { randomId } from "./crypto";
import type { LicenseStatus, LicenseType } from "./config";

export interface CustomerRow {
  id: string;
  email: string;
  stripe_customer_id: string | null;
}

export interface LicenseRow {
  id: string;
  customer_id: string;
  product: string;
  type: LicenseType;
  status: LicenseStatus;
  max_devices: number;
  stripe_customer_id: string | null;
  stripe_subscription_id: string | null;
  stripe_price_id: string | null;
  current_period_end: number | null;
  created_at: number;
  updated_at: number;
  last_stripe_sync: number | null;
}

export interface DeviceRow {
  id: string;
  license_id: string;
  machine_id: string;
  device_name: string | null;
  activated_at: number;
  last_verified_at: number | null;
  deactivated_at: number | null;
  status: "active" | "deactivated";
  activation_method: "email" | "key";
  activation_key_generation: number | null;
  app_version: string | null;
  os_version: string | null;
  architecture: string | null;
}

export interface ActivationKeyRow {
  license_id: string;
  generation: number;
  verifier_hash: string;
  ciphertext: string;
  nonce: string;
  created_at: number;
  rotated_at: number | null;
}

export interface DeviceMetadata {
  appVersion: string | null;
  osVersion: string | null;
  architecture: string | null;
}

export interface PortalSessionRow {
  id: string;
  customer_id: string;
  token_hash: string;
  created_at: number;
  expires_at: number;
  last_seen_at: number;
  revoked_at: number | null;
  csrf_token_hash: string | null;
}

export interface PasswordCredentialRow {
  customer_id: string;
  password_hash: string;
  created_at: number;
  updated_at: number;
  password_changed_at: number;
}

export interface PasswordResetCodeRow {
  id: string;
  customer_id: string;
  email: string;
  code_hash: string;
  created_at: number;
  expires_at: number;
  attempt_count: number;
  used_at: number | null;
}

export interface PortalProfileRow {
  customer_id: string;
  first_name: string;
  last_name: string;
  club_name: string | null;
  created_at: number;
  updated_at: number;
}

export interface PortalRegistrationChallengeRow {
  id: string;
  customer_id: string | null;
  email: string;
  code_hash: string;
  setup_token_hash: string | null;
  purpose: "registration" | "migration";
  created_at: number;
  expires_at: number;
  attempt_count: number;
  verified_at: number | null;
  completed_at: number | null;
}

export function now(): number {
  return Math.floor(Date.now() / 1000);
}

export function normaliseEmail(value: string): string {
  return value.trim().toLowerCase();
}

export async function logEvent(
  db: D1Database,
  type: string,
  licenseId: string | null,
  detail?: Record<string, unknown>,
): Promise<void> {
  // Detail is for operators. Never pass verification codes, tokens or secrets.
  await db
    .prepare("INSERT INTO events (id, license_id, type, detail, created_at) VALUES (?, ?, ?, ?, ?)")
    .bind(randomId("evt"), licenseId, type, detail ? JSON.stringify(detail) : null, now())
    .run();
}

export async function findCustomerByEmail(db: D1Database, email: string): Promise<CustomerRow | null> {
  return db
    .prepare("SELECT id, email, stripe_customer_id FROM customers WHERE email = ?")
    .bind(normaliseEmail(email))
    .first<CustomerRow>();
}

export async function findCustomerById(db: D1Database, customerId: string): Promise<CustomerRow | null> {
  return db
    .prepare("SELECT id, email, stripe_customer_id FROM customers WHERE id = ?")
    .bind(customerId)
    .first<CustomerRow>();
}

export async function upsertCustomer(
  db: D1Database,
  email: string,
  stripeCustomerId: string | null,
): Promise<CustomerRow> {
  const normalised = normaliseEmail(email);
  const existing = await findCustomerByEmail(db, normalised);
  if (existing) {
    if (stripeCustomerId && existing.stripe_customer_id !== stripeCustomerId) {
      await db
        .prepare("UPDATE customers SET stripe_customer_id = ?, updated_at = ? WHERE id = ?")
        .bind(stripeCustomerId, now(), existing.id)
        .run();
      return { ...existing, stripe_customer_id: stripeCustomerId };
    }
    return existing;
  }
  const id = randomId("cus");
  const timestamp = now();
  await db
    .prepare(
      "INSERT INTO customers (id, email, stripe_customer_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
    )
    .bind(id, normalised, stripeCustomerId, timestamp, timestamp)
    .run();
  return { id, email: normalised, stripe_customer_id: stripeCustomerId };
}

/**
 * The licence a customer activates with. A customer could in principle own
 * several; the most recently created active one wins, which matches the
 * common case of someone upgrading from subscription to lifetime.
 */
export async function findActivatableLicense(db: D1Database, email: string): Promise<LicenseRow | null> {
  return db
    .prepare(
      `SELECT l.* FROM licenses l
         JOIN customers c ON c.id = l.customer_id
        WHERE c.email = ? AND l.status = 'active'
        ORDER BY CASE l.type WHEN 'lifetime' THEN 0 ELSE 1 END, l.created_at DESC
        LIMIT 1`,
    )
    .bind(normaliseEmail(email))
    .first<LicenseRow>();
}

export async function listLicensesForCustomer(db: D1Database, customerId: string): Promise<LicenseRow[]> {
  const result = await db
    .prepare("SELECT * FROM licenses WHERE customer_id = ? ORDER BY created_at DESC")
    .bind(customerId)
    .all<LicenseRow>();
  return result.results ?? [];
}

export async function listDevicesForCustomer(db: D1Database, customerId: string): Promise<DeviceRow[]> {
  const result = await db
    .prepare(
      `SELECT d.* FROM devices d
         JOIN licenses l ON l.id = d.license_id
        WHERE l.customer_id = ?
        ORDER BY d.status ASC, d.activated_at DESC`,
    )
    .bind(customerId)
    .all<DeviceRow>();
  return result.results ?? [];
}

export async function findLicenseById(db: D1Database, id: string): Promise<LicenseRow | null> {
  return db.prepare("SELECT * FROM licenses WHERE id = ?").bind(id).first<LicenseRow>();
}

export async function findLicenseBySubscription(
  db: D1Database,
  subscriptionId: string,
): Promise<LicenseRow | null> {
  return db
    .prepare("SELECT * FROM licenses WHERE stripe_subscription_id = ?")
    .bind(subscriptionId)
    .first<LicenseRow>();
}

export async function createLicense(
  db: D1Database,
  fields: {
    customerId: string;
    type: LicenseType;
    maxDevices: number;
    stripeCustomerId: string | null;
    stripeSubscriptionId: string | null;
    stripePriceId: string | null;
    currentPeriodEnd: number | null;
  },
): Promise<LicenseRow> {
  const id = randomId("lic");
  const timestamp = now();
  await db
    .prepare(
      `INSERT INTO licenses
         (id, customer_id, product, type, status, max_devices, stripe_customer_id,
          stripe_subscription_id, stripe_price_id, current_period_end,
          created_at, updated_at, last_stripe_sync)
       VALUES (?, ?, 'LongJumpReplay', ?, 'active', ?, ?, ?, ?, ?, ?, ?, ?)`,
    )
    .bind(
      id,
      fields.customerId,
      fields.type,
      fields.maxDevices,
      fields.stripeCustomerId,
      fields.stripeSubscriptionId,
      fields.stripePriceId,
      fields.currentPeriodEnd,
      timestamp,
      timestamp,
      timestamp,
    )
    .run();
  return (await findLicenseById(db, id))!;
}

export async function setLicenseStatus(
  db: D1Database,
  licenseId: string,
  status: LicenseStatus,
  currentPeriodEnd?: number | null,
): Promise<number> {
  const timestamp = now();
  const licenseUpdate = currentPeriodEnd === undefined
    ? db.prepare("UPDATE licenses SET status = ?, updated_at = ?, last_stripe_sync = ? WHERE id = ?")
      .bind(status, timestamp, timestamp, licenseId)
    : db.prepare(
      "UPDATE licenses SET status = ?, current_period_end = ?, updated_at = ?, last_stripe_sync = ? WHERE id = ?",
    ).bind(status, currentPeriodEnd, timestamp, timestamp, licenseId);

  // A terminal subscription must revoke every active computer immediately.
  // Keeping both statements in one D1 batch prevents a half-applied
  // cancellation where the licence is inactive but a device remains usable.
  const statements = [licenseUpdate];
  if (status === "inactive") {
    statements.push(
      db.prepare(`UPDATE devices SET status = 'deactivated', deactivated_at = ?
        WHERE license_id = ? AND status = 'active'`).bind(timestamp, licenseId),
    );
  }
  const results = await db.batch(statements);
  return status === "inactive" ? (results[1]?.meta.changes ?? 0) : 0;
}

export async function activeDeviceCount(db: D1Database, licenseId: string): Promise<number> {
  const row = await db
    .prepare("SELECT COUNT(*) AS n FROM devices WHERE license_id = ? AND status = 'active'")
    .bind(licenseId)
    .first<{ n: number }>();
  return row?.n ?? 0;
}

export async function findDevice(
  db: D1Database,
  licenseId: string,
  machineId: string,
): Promise<DeviceRow | null> {
  return db
    .prepare("SELECT * FROM devices WHERE license_id = ? AND machine_id = ?")
    .bind(licenseId, machineId)
    .first<DeviceRow>();
}

/** Re-activating a known machine refreshes it instead of consuming a seat. */
export async function activateDevice(
  db: D1Database,
  licenseId: string,
  machineId: string,
  deviceName: string | null,
  activationMethod: "email" | "key" = "email",
  activationKeyGeneration: number | null = null,
  metadata: DeviceMetadata = { appVersion: null, osVersion: null, architecture: null },
): Promise<DeviceRow> {
  const existing = await findDevice(db, licenseId, machineId);
  const timestamp = now();
  if (existing) {
    await db
      .prepare(
        `UPDATE devices SET status = 'active', deactivated_at = NULL, last_verified_at = ?,
          device_name = COALESCE(?, device_name), activation_method = ?, activation_key_generation = ?,
          app_version = COALESCE(?, app_version), os_version = COALESCE(?, os_version),
          architecture = COALESCE(?, architecture) WHERE id = ?`,
      )
      .bind(timestamp, deviceName, activationMethod, activationKeyGeneration, metadata.appVersion, metadata.osVersion, metadata.architecture, existing.id)
      .run();
    return { ...existing, status: "active", last_verified_at: timestamp, activation_method: activationMethod,
      activation_key_generation: activationKeyGeneration, app_version: metadata.appVersion ?? existing.app_version,
      os_version: metadata.osVersion ?? existing.os_version, architecture: metadata.architecture ?? existing.architecture };
  }
  const id = randomId("dev");
  await db
    .prepare(
      `INSERT INTO devices (id, license_id, machine_id, device_name, activated_at, last_verified_at, status,
        activation_method, activation_key_generation, app_version, os_version, architecture)
       VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?)`,
    )
    .bind(id, licenseId, machineId, deviceName, timestamp, timestamp, activationMethod, activationKeyGeneration,
      metadata.appVersion, metadata.osVersion, metadata.architecture)
    .run();
  return {
    id,
    license_id: licenseId,
    machine_id: machineId,
    device_name: deviceName,
    activated_at: timestamp,
    last_verified_at: timestamp,
    deactivated_at: null,
    status: "active",
    activation_method: activationMethod,
    activation_key_generation: activationKeyGeneration,
    app_version: metadata.appVersion,
    os_version: metadata.osVersion,
    architecture: metadata.architecture,
  };
}

export async function deactivateDevice(db: D1Database, licenseId: string, machineId: string): Promise<boolean> {
  const result = await db
    .prepare(
      "UPDATE devices SET status = 'deactivated', deactivated_at = ? WHERE license_id = ? AND machine_id = ? AND status = 'active'",
    )
    .bind(now(), licenseId, machineId)
    .run();
  return (result.meta.changes ?? 0) > 0;
}

export async function deactivateDeviceForCustomer(
  db: D1Database,
  customerId: string,
  deviceId: string,
): Promise<{ removed: boolean; licenseId: string | null }> {
  const result = await db
    .prepare(
      `UPDATE devices SET status = 'deactivated', deactivated_at = ?
         WHERE id = ? AND status = 'active'
           AND license_id IN (SELECT id FROM licenses WHERE customer_id = ?)`,
    )
    .bind(now(), deviceId, customerId)
    .run();
  if ((result.meta.changes ?? 0) === 0) return { removed: false, licenseId: null };
  const row = await db
    .prepare("SELECT license_id FROM devices WHERE id = ?")
    .bind(deviceId)
    .first<{ license_id: string }>();
  return { removed: true, licenseId: row?.license_id ?? null };
}

export async function createPortalSession(
  db: D1Database,
  customerId: string,
  tokenHash: string,
  expiresAt: number,
  csrfTokenHash: string | null = null,
): Promise<PortalSessionRow> {
  const timestamp = now();
  const id = randomId("portal");
  await db
    .prepare(
      `INSERT INTO portal_sessions
         (id, customer_id, token_hash, created_at, expires_at, last_seen_at, csrf_token_hash)
       VALUES (?, ?, ?, ?, ?, ?, ?)`,
    )
    .bind(id, customerId, tokenHash, timestamp, expiresAt, timestamp, csrfTokenHash)
    .run();
  return { id, customer_id: customerId, token_hash: tokenHash, created_at: timestamp, expires_at: expiresAt, last_seen_at: timestamp, revoked_at: null, csrf_token_hash: csrfTokenHash };
}

export async function findPortalSession(db: D1Database, tokenHash: string): Promise<PortalSessionRow | null> {
  return db
    .prepare("SELECT * FROM portal_sessions WHERE token_hash = ? AND revoked_at IS NULL")
    .bind(tokenHash)
    .first<PortalSessionRow>();
}

export async function touchPortalSession(db: D1Database, sessionId: string): Promise<void> {
  await db.prepare("UPDATE portal_sessions SET last_seen_at = ? WHERE id = ?").bind(now(), sessionId).run();
}

export async function revokePortalSession(db: D1Database, tokenHash: string): Promise<void> {
  await db.prepare("UPDATE portal_sessions SET revoked_at = ? WHERE token_hash = ? AND revoked_at IS NULL").bind(now(), tokenHash).run();
}

export async function revokePortalSessionsForCustomer(db: D1Database, customerId: string): Promise<void> {
  await db.prepare("UPDATE portal_sessions SET revoked_at = ? WHERE customer_id = ? AND revoked_at IS NULL").bind(now(), customerId).run();
}

export async function findPasswordCredential(db: D1Database, customerId: string): Promise<PasswordCredentialRow | null> {
  return db.prepare("SELECT * FROM customer_password_credentials WHERE customer_id = ?")
    .bind(customerId).first<PasswordCredentialRow>();
}

export async function createPasswordCredential(db: D1Database, customerId: string, passwordHash: string): Promise<void> {
  const timestamp = now();
  await db.prepare(`INSERT INTO customer_password_credentials
    (customer_id, password_hash, created_at, updated_at, password_changed_at)
    VALUES (?, ?, ?, ?, ?)`)
    .bind(customerId, passwordHash, timestamp, timestamp, timestamp).run();
}

export async function updatePasswordCredential(db: D1Database, customerId: string, passwordHash: string): Promise<void> {
  const timestamp = now();
  await db.prepare(`UPDATE customer_password_credentials
    SET password_hash = ?, updated_at = ?, password_changed_at = ? WHERE customer_id = ?`)
    .bind(passwordHash, timestamp, timestamp, customerId).run();
}

export async function createPasswordResetCode(
  db: D1Database,
  customerId: string,
  email: string,
  codeHash: string,
  expiresAt: number,
): Promise<PasswordResetCodeRow> {
  const timestamp = now();
  const row = { id: randomId("prc"), customer_id: customerId, email, code_hash: codeHash,
    created_at: timestamp, expires_at: expiresAt, attempt_count: 0, used_at: null };
  await db.prepare(`INSERT INTO password_reset_codes
    (id, customer_id, email, code_hash, created_at, expires_at, attempt_count)
    VALUES (?, ?, ?, ?, ?, ?, 0)`)
    .bind(row.id, row.customer_id, row.email, row.code_hash, row.created_at, row.expires_at).run();
  return row;
}

export async function invalidatePasswordResetCodes(db: D1Database, customerId: string): Promise<void> {
  await db.prepare("UPDATE password_reset_codes SET used_at = ? WHERE customer_id = ? AND used_at IS NULL")
    .bind(now(), customerId).run();
}

export async function findLatestPasswordResetCode(db: D1Database, email: string): Promise<PasswordResetCodeRow | null> {
  return db.prepare(`SELECT * FROM password_reset_codes
    WHERE email = ? AND used_at IS NULL ORDER BY created_at DESC LIMIT 1`)
    .bind(email).first<PasswordResetCodeRow>();
}

export async function incrementPasswordResetAttempts(db: D1Database, id: string): Promise<void> {
  await db.prepare("UPDATE password_reset_codes SET attempt_count = attempt_count + 1 WHERE id = ?").bind(id).run();
}

export async function consumePasswordResetCode(db: D1Database, id: string): Promise<boolean> {
  const result = await db.prepare("UPDATE password_reset_codes SET used_at = ? WHERE id = ? AND used_at IS NULL").bind(now(), id).run();
  return (result.meta.changes ?? 0) === 1;
}

export async function findPortalProfile(db: D1Database, customerId: string): Promise<PortalProfileRow | null> {
  return db.prepare("SELECT * FROM portal_profiles WHERE customer_id = ?")
    .bind(customerId).first<PortalProfileRow>();
}

export async function savePortalProfile(
  db: D1Database,
  customerId: string,
  firstName: string,
  lastName: string,
  clubName: string | null,
): Promise<void> {
  const timestamp = now();
  await db.prepare(`INSERT INTO portal_profiles
      (customer_id, first_name, last_name, club_name, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?)
    ON CONFLICT(customer_id) DO UPDATE SET
      first_name = excluded.first_name,
      last_name = excluded.last_name,
      club_name = excluded.club_name,
      updated_at = excluded.updated_at`)
    .bind(customerId, firstName, lastName, clubName, timestamp, timestamp).run();
}

export async function invalidatePortalRegistrationChallenges(
  db: D1Database,
  email: string,
  purpose: "registration" | "migration",
): Promise<void> {
  await db.prepare(`UPDATE portal_registration_challenges
      SET completed_at = COALESCE(completed_at, ?)
    WHERE email = ? AND purpose = ? AND completed_at IS NULL`)
    .bind(now(), normaliseEmail(email), purpose).run();
}

export async function createPortalRegistrationChallenge(
  db: D1Database,
  customerId: string | null,
  email: string,
  codeHash: string,
  purpose: "registration" | "migration",
  expiresAt: number,
): Promise<PortalRegistrationChallengeRow> {
  const timestamp = now();
  const row: PortalRegistrationChallengeRow = {
    id: randomId("reg"), customer_id: customerId, email: normaliseEmail(email),
    code_hash: codeHash, setup_token_hash: null, purpose, created_at: timestamp,
    expires_at: expiresAt, attempt_count: 0, verified_at: null, completed_at: null,
  };
  await db.prepare(`INSERT INTO portal_registration_challenges
      (id, customer_id, email, code_hash, purpose, created_at, expires_at, attempt_count)
    VALUES (?, ?, ?, ?, ?, ?, ?, 0)`)
    .bind(row.id, row.customer_id, row.email, row.code_hash, row.purpose, row.created_at, row.expires_at).run();
  return row;
}

export async function findLatestPortalRegistrationChallenge(
  db: D1Database,
  email: string,
  purpose: "registration" | "migration",
): Promise<PortalRegistrationChallengeRow | null> {
  return db.prepare(`SELECT * FROM portal_registration_challenges
      WHERE email = ? AND purpose = ? AND completed_at IS NULL
    ORDER BY created_at DESC LIMIT 1`)
    .bind(normaliseEmail(email), purpose).first<PortalRegistrationChallengeRow>();
}

export async function findPortalRegistrationChallengeBySetupToken(
  db: D1Database,
  setupTokenHash: string,
): Promise<PortalRegistrationChallengeRow | null> {
  return db.prepare(`SELECT * FROM portal_registration_challenges
      WHERE setup_token_hash = ? AND verified_at IS NOT NULL AND completed_at IS NULL
    ORDER BY created_at DESC LIMIT 1`)
    .bind(setupTokenHash).first<PortalRegistrationChallengeRow>();
}

export async function incrementPortalRegistrationAttempts(db: D1Database, id: string): Promise<void> {
  await db.prepare("UPDATE portal_registration_challenges SET attempt_count = attempt_count + 1 WHERE id = ?")
    .bind(id).run();
}

export async function markPortalRegistrationVerified(
  db: D1Database,
  id: string,
  setupTokenHash: string,
): Promise<boolean> {
  const result = await db.prepare(`UPDATE portal_registration_challenges
      SET verified_at = ?, setup_token_hash = ?
    WHERE id = ? AND verified_at IS NULL AND completed_at IS NULL`)
    .bind(now(), setupTokenHash, id).run();
  return (result.meta.changes ?? 0) === 1;
}

export async function completePortalRegistrationChallenge(db: D1Database, id: string): Promise<boolean> {
  const result = await db.prepare(`UPDATE portal_registration_challenges
      SET completed_at = ?
    WHERE id = ? AND verified_at IS NOT NULL AND completed_at IS NULL`)
    .bind(now(), id).run();
  return (result.meta.changes ?? 0) === 1;
}

export async function touchDevice(db: D1Database, deviceId: string, metadata?: DeviceMetadata): Promise<void> {
  await db.prepare(`UPDATE devices SET last_verified_at = ?, app_version = COALESCE(?, app_version),
    os_version = COALESCE(?, os_version), architecture = COALESCE(?, architecture) WHERE id = ?`)
    .bind(now(), metadata?.appVersion ?? null, metadata?.osVersion ?? null, metadata?.architecture ?? null, deviceId).run();
}

export async function findActivationKeyByLicense(db: D1Database, licenseId: string): Promise<ActivationKeyRow | null> {
  return db.prepare("SELECT * FROM license_activation_keys WHERE license_id = ?").bind(licenseId).first<ActivationKeyRow>();
}

export async function findActivationKeyByVerifier(db: D1Database, verifierHash: string): Promise<(ActivationKeyRow & LicenseRow) | null> {
  return db.prepare(`SELECT k.license_id AS key_license_id, k.generation, k.verifier_hash, k.ciphertext, k.nonce,
      k.created_at AS key_created_at, k.rotated_at, l.* FROM license_activation_keys k
      JOIN licenses l ON l.id = k.license_id WHERE k.verifier_hash = ?`)
    .bind(verifierHash).first<ActivationKeyRow & LicenseRow>();
}

export async function saveActivationKey(db: D1Database, row: Omit<ActivationKeyRow, "created_at" | "rotated_at">): Promise<void> {
  const timestamp = now();
  await db.prepare(`INSERT INTO license_activation_keys
      (license_id, generation, verifier_hash, ciphertext, nonce, created_at)
      VALUES (?, ?, ?, ?, ?, ?)`)
    .bind(row.license_id, row.generation, row.verifier_hash, row.ciphertext, row.nonce, timestamp).run();
}

export async function rotateActivationKey(db: D1Database, licenseId: string, generation: number,
  verifierHash: string, ciphertext: string, nonce: string): Promise<number> {
  const timestamp = now();
  const results = await db.batch([
    db.prepare(`UPDATE license_activation_keys SET generation = ?, verifier_hash = ?, ciphertext = ?, nonce = ?, rotated_at = ?
      WHERE license_id = ?`).bind(generation, verifierHash, ciphertext, nonce, timestamp, licenseId),
    db.prepare(`UPDATE devices SET status = 'deactivated', deactivated_at = ? WHERE license_id = ?
      AND activation_method = 'key' AND status = 'active'`).bind(timestamp, licenseId),
  ]);
  return results[1].meta.changes ?? 0;
}

export async function recordDeviceActivity(db: D1Database, device: DeviceRow, eventType: "activation" | "verification",
  network: { ipAddress: string | null; country: string | null }, metadata: DeviceMetadata): Promise<void> {
  await db.prepare(`INSERT INTO device_activity
      (id, device_id, license_id, event_type, ip_address, country, app_version, os_version, architecture, created_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`)
    .bind(randomId("activity"), device.id, device.license_id, eventType, network.ipAddress, network.country,
      metadata.appVersion, metadata.osVersion, metadata.architecture, now()).run();
}

export async function deviceDetailsForCustomer(db: D1Database, customerId: string, deviceId: string) {
  const device = await db.prepare(`SELECT d.* FROM devices d JOIN licenses l ON l.id = d.license_id
    WHERE d.id = ? AND l.customer_id = ?`).bind(deviceId, customerId).first<DeviceRow>();
  if (!device) return null;
  const activity = await db.prepare(`SELECT event_type, ip_address, country, app_version, os_version, architecture, created_at
    FROM device_activity WHERE device_id = ? ORDER BY created_at DESC LIMIT 100`).bind(deviceId).all();
  return { device, activity: activity.results ?? [] };
}

export async function deleteDeactivatedDeviceForCustomer(db: D1Database, customerId: string, deviceId: string): Promise<{ deleted: boolean; licenseId: string | null }> {
  const device = await db.prepare(`SELECT d.id, d.license_id FROM devices d JOIN licenses l ON l.id = d.license_id
    WHERE d.id = ? AND d.status = 'deactivated' AND l.customer_id = ?`).bind(deviceId, customerId)
    .first<{ id: string; license_id: string }>();
  if (!device) return { deleted: false, licenseId: null };
  await db.batch([
    db.prepare("DELETE FROM device_activity WHERE device_id = ?").bind(deviceId),
    db.prepare("DELETE FROM devices WHERE id = ? AND status = 'deactivated'").bind(deviceId),
  ]);
  return { deleted: true, licenseId: device.license_id };
}

export async function purgeOldDeviceActivity(db: D1Database, cutoff: number): Promise<number> {
  const result = await db.prepare("DELETE FROM device_activity WHERE created_at < ?").bind(cutoff).run();
  return result.meta.changes ?? 0;
}

/** Returns false when the event was already handled - the idempotency guard. */
export async function claimStripeEvent(db: D1Database, id: string, type: string): Promise<boolean> {
  try {
    await db
      .prepare("INSERT INTO stripe_events (id, type, processed_at) VALUES (?, ?, ?)")
      .bind(id, type, now())
      .run();
    return true;
  } catch {
    // Primary key collision: a redelivery of an event already processed.
    return false;
  }
}

export async function applyAdditionalComputerPurchase(
  db: D1Database,
  purchase: { stripeSessionId: string; stripePaymentIntentId: string | null; customerId: string; licenseId: string; quantity: number; amount: number; currency: string },
): Promise<{ applied: boolean; duplicate: boolean; resultingMaxDevices: number | null }> {
  const timestamp = now();
  try {
    const result = await db.batch([
      db.prepare(`INSERT INTO additional_computer_purchases
        (stripe_session_id, stripe_payment_intent_id, customer_id, license_id, quantity, amount, currency, processed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)`).bind(purchase.stripeSessionId, purchase.stripePaymentIntentId, purchase.customerId, purchase.licenseId, purchase.quantity, purchase.amount, purchase.currency, timestamp),
      db.prepare(`UPDATE licenses SET max_devices = max_devices + ?, updated_at = ?
        WHERE id = ? AND customer_id = ? AND type = 'lifetime' AND status = 'active'
          AND max_devices + ? <= 10`).bind(purchase.quantity, timestamp, purchase.licenseId, purchase.customerId, purchase.quantity),
    ]);
    const applied = (result[1].meta.changes ?? 0) === 1;
    const license = await findLicenseById(db, purchase.licenseId);
    await db.prepare("UPDATE additional_computer_purchases SET resulting_max_devices = ? WHERE stripe_session_id = ?")
      .bind(applied ? license?.max_devices ?? null : null, purchase.stripeSessionId).run();
    return { applied, duplicate: false, resultingMaxDevices: applied ? license?.max_devices ?? null : null };
  } catch (error) {
    const existing = await db.prepare("SELECT resulting_max_devices FROM additional_computer_purchases WHERE stripe_session_id = ?")
      .bind(purchase.stripeSessionId).first<{ resulting_max_devices: number | null }>();
    if (existing) return { applied: false, duplicate: true, resultingMaxDevices: existing.resulting_max_devices };
    throw error;
  }
}
/**
 * Fixed-window counter in D1. Good enough for the volumes here, and avoids a
 * second binding just for rate limiting.
 */
export async function rateLimit(
  db: D1Database,
  bucket: string,
  max: number,
  windowSeconds: number,
): Promise<boolean> {
  const current = now();
  const row = await db
    .prepare("SELECT count, window_start FROM rate_limits WHERE bucket = ?")
    .bind(bucket)
    .first<{ count: number; window_start: number }>();

  if (!row || current - row.window_start >= windowSeconds) {
    await db
      .prepare(
        `INSERT INTO rate_limits (bucket, count, window_start) VALUES (?, 1, ?)
         ON CONFLICT (bucket) DO UPDATE SET count = 1, window_start = excluded.window_start`,
      )
      .bind(bucket, current)
      .run();
    return true;
  }
  if (row.count >= max) return false;
  await db.prepare("UPDATE rate_limits SET count = count + 1 WHERE bucket = ?").bind(bucket).run();
  return true;
}

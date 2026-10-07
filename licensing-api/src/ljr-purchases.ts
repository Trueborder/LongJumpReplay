import { randomId } from "./crypto";
import { now } from "./db";
import type { LicenseType } from "./config";

export const LJR_POLICY_VERSIONS = {
  purchase: "2026-10-07",
  eula: "2026-10-07",
  refund: "2026-10-07",
  privacy: "2026-10-07",
  consent: "2026-10-07",
  activation: "2026-10-07",
  updates: "2026-10-07",
} as const;

export interface LjrOrder {
  id: string; customer_id: string | null; email: string; product_id: string;
  stripe_product_id: string | null; stripe_price_id: string; product_name: string;
  license_type: LicenseType; displayed_price_minor: number; currency: string; tax_notice: string;
  purchase_terms_version: string; eula_version: string; refund_policy_version: string;
  privacy_policy_version: string; consent_version: string; terms_accepted_at: number;
  immediate_delivery_requested_at: number; withdrawal_acknowledged_at: number;
  idempotency_key: string;
  stripe_checkout_session_id: string | null; stripe_customer_id: string | null;
  payment_intent_id: string | null; stripe_subscription_id: string | null; license_id: string | null;
  status: string; delivery_status: string; confirmation_status: string; receipt_reference: string | null;
  refund_status: string | null; dispute_status: string | null; entitlement_status: string;
  paid_at: number | null; created_at: number; updated_at: number;
}

export type LjrOrderCreate = Omit<LjrOrder, "status" | "delivery_status" | "confirmation_status" | "entitlement_status" | "paid_at" | "updated_at" | "stripe_checkout_session_id" | "stripe_customer_id" | "payment_intent_id" | "stripe_subscription_id" | "license_id" | "receipt_reference" | "refund_status" | "dispute_status"> & { idempotency_key: string; consent_ip: string | null; consent_user_agent: string | null };

export async function findLjrOrderByIdempotency(db: D1Database, key: string): Promise<LjrOrder | null> {
  return db.prepare("SELECT * FROM ljr_orders WHERE idempotency_key=?").bind(key).first<LjrOrder>();
}

export async function findLjrOrderById(db: D1Database, id: string): Promise<LjrOrder | null> {
  return db.prepare("SELECT * FROM ljr_orders WHERE id=?").bind(id).first<LjrOrder>();
}

export async function findLjrOrderBySession(db: D1Database, sessionId: string): Promise<LjrOrder | null> {
  return db.prepare("SELECT * FROM ljr_orders WHERE stripe_checkout_session_id=?").bind(sessionId).first<LjrOrder>();
}

export async function findLjrOrderByPaymentIntent(db: D1Database, paymentIntent: string): Promise<LjrOrder | null> {
  return db.prepare("SELECT * FROM ljr_orders WHERE payment_intent_id=?").bind(paymentIntent).first<LjrOrder>();
}

export async function listLjrOrdersForCustomer(db: D1Database, customerId: string): Promise<LjrOrder[]> {
  const result = await db.prepare("SELECT * FROM ljr_orders WHERE customer_id=? ORDER BY created_at DESC LIMIT 100").bind(customerId).all<LjrOrder>();
  return result.results ?? [];
}

export async function createLjrOrder(db: D1Database, order: LjrOrderCreate): Promise<LjrOrder> {
  const timestamp = now();
  await db.prepare(`INSERT INTO ljr_orders
    (id,customer_id,email,product_id,stripe_product_id,stripe_price_id,product_name,license_type,displayed_price_minor,currency,tax_notice,
     purchase_terms_version,eula_version,refund_policy_version,privacy_policy_version,consent_version,terms_accepted_at,
     immediate_delivery_requested_at,withdrawal_acknowledged_at,consent_ip,consent_user_agent,idempotency_key,status,delivery_status,
     confirmation_status,entitlement_status,created_at,updated_at)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'checkout_pending','pending','pending','pending',?,?)`).bind(
      order.id, order.customer_id, order.email, order.product_id, order.stripe_product_id, order.stripe_price_id, order.product_name,
      order.license_type, order.displayed_price_minor, order.currency, order.tax_notice, order.purchase_terms_version, order.eula_version,
      order.refund_policy_version, order.privacy_policy_version, order.consent_version, order.terms_accepted_at,
      order.immediate_delivery_requested_at, order.withdrawal_acknowledged_at, order.consent_ip, order.consent_user_agent,
      order.idempotency_key, timestamp, timestamp,
    ).run();
  return (await findLjrOrderById(db, order.id))!;
}

export async function updateLjrOrderCheckout(db: D1Database, orderId: string, sessionId: string): Promise<void> {
  await db.prepare("UPDATE ljr_orders SET stripe_checkout_session_id=?, updated_at=? WHERE id=?").bind(sessionId, now(), orderId).run();
}

export async function updateLjrOrder(db: D1Database, orderId: string, fields: Record<string, unknown>): Promise<void> {
  const allowed = new Set(["customer_id","stripe_customer_id","payment_intent_id","stripe_subscription_id","license_id","status","delivery_status","confirmation_status","receipt_reference","refund_status","dispute_status","entitlement_status","paid_at"]);
  const entries = Object.entries(fields).filter(([key]) => allowed.has(key));
  if (!entries.length) return;
  const values = entries.map(([key]) => `${key}=?`).join(",");
  await db.prepare(`UPDATE ljr_orders SET ${values}, updated_at=? WHERE id=?`).bind(...entries.map(([, value]) => value), now(), orderId).run();
}

export async function appendLjrOrderEvent(db: D1Database, orderId: string, eventType: string, stripeEventId: string | null, detail?: Record<string, unknown>): Promise<void> {
  await db.prepare("INSERT INTO ljr_order_events(id,order_id,event_type,stripe_event_id,detail,created_at) VALUES(?,?,?,?,?,?)")
    .bind(randomId("ljr_evt"), orderId, eventType, stripeEventId, detail ? JSON.stringify(detail) : null, now()).run();
}

export function publicLjrOrder(order: LjrOrder) {
  return { id: order.id, product_id: order.product_id, product_name: order.product_name, license_type: order.license_type,
    displayed_price_minor: order.displayed_price_minor, currency: order.currency, status: order.status,
    delivery_status: order.delivery_status, confirmation_status: order.confirmation_status, receipt_reference: order.receipt_reference,
    refund_status: order.refund_status, dispute_status: order.dispute_status, entitlement_status: order.entitlement_status,
    license_id: order.license_id, paid_at: order.paid_at, created_at: order.created_at, updated_at: order.updated_at };
}

/**
 * Stripe webhook signature verification and event handling.
 *
 * Signatures are verified manually rather than with the Stripe SDK, following
 * https://docs.stripe.com/webhooks#verify-manually. Without this an attacker who
 * learns the endpoint URL could post a forged "payment succeeded" event and be
 * issued a free licence.
 */

const encoder = new TextEncoder();

/** Stripe's own libraries default to five minutes. */
export const DEFAULT_TOLERANCE_SECONDS = 300;

export class SignatureError extends Error {}

function parseHeader(header: string): { timestamp: number; signatures: string[] } {
  let timestamp: number | null = null;
  const signatures: string[] = [];
  for (const element of header.split(",")) {
    const index = element.indexOf("=");
    if (index < 0) continue;
    const prefix = element.slice(0, index).trim();
    const value = element.slice(index + 1).trim();
    if (prefix === "t") {
      const parsed = Number.parseInt(value, 10);
      if (!Number.isFinite(parsed)) throw new SignatureError("malformed timestamp");
      timestamp = parsed;
    } else if (prefix === "v1") {
      // Only v1 is trusted. Stripe also sends a fake v0 on test events, and
      // accepting other schemes would invite a downgrade attack.
      signatures.push(value);
    }
  }
  if (timestamp === null) throw new SignatureError("no timestamp in Stripe-Signature");
  if (signatures.length === 0) throw new SignatureError("no v1 signature in Stripe-Signature");
  return { timestamp, signatures };
}

function toHex(buffer: ArrayBuffer): string {
  return [...new Uint8Array(buffer)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function constantTimeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i += 1) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

/**
 * `payload` must be the exact bytes Stripe sent. Re-serialising the JSON first
 * will fail verification.
 */
export async function verifySignature(
  payload: string,
  header: string | null,
  secret: string,
  toleranceSeconds = DEFAULT_TOLERANCE_SECONDS,
  now = Math.floor(Date.now() / 1000),
): Promise<void> {
  if (!secret) throw new SignatureError("no webhook signing secret configured");
  if (!header) throw new SignatureError("missing Stripe-Signature header");
  if (toleranceSeconds <= 0) throw new SignatureError("tolerance must be positive");

  const { timestamp, signatures } = parseHeader(header);
  if (Math.abs(now - timestamp) > toleranceSeconds) throw new SignatureError("timestamp outside tolerance");

  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const expected = toHex(await crypto.subtle.sign("HMAC", key, encoder.encode(`${timestamp}.${payload}`)));

  // Stripe sends one signature per active secret while a secret is rolling.
  if (!signatures.some((candidate) => constantTimeEqual(expected, candidate))) {
    throw new SignatureError("no signature matched the expected value");
  }
}

/** Minimal shapes; only the fields this Worker actually reads. */
export interface StripeEvent {
  id: string;
  type: string;
  data: { object: Record<string, any> };
}

export interface StripeApi {
  getSubscription(id: string): Promise<Record<string, any>>;
  getCheckoutLineItems(sessionId: string): Promise<Record<string, any>[]>;
  getInvoices(customerId: string): Promise<Record<string, any>[]>;
  createBillingPortalSession(customerId: string, returnUrl: string): Promise<string>;
  createAdditionalComputerCheckout(input: { customerId: string; licenseId: string; quantity: number; pricesCzk: number[]; successUrl: string; cancelUrl: string }): Promise<string>;
}

/**
 * Thin REST client. Used only to read back data the webhook payload does not
 * always carry - notably the price ID on a checkout session.
 */
export function stripeApi(secretKey: string): StripeApi {
  async function get(path: string): Promise<Record<string, any>> {
    const response = await fetch(`https://api.stripe.com/v1/${path}`, {
      headers: { Authorization: `Bearer ${secretKey}` },
    });
    if (!response.ok) {
      // Deliberately does not include the response body, which can echo request
      // details, and never the key.
      throw new Error(`Stripe API ${path} failed with ${response.status}`);
    }
    return (await response.json()) as Record<string, any>;
  }

  async function postForm(path: string, values: Record<string, string>): Promise<Record<string, any>> {
    const response = await fetch(`https://api.stripe.com/v1/${path}`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${secretKey}`,
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: new URLSearchParams(values),
    });
    if (!response.ok) throw new Error(`Stripe API ${path} failed with ${response.status}`);
    return (await response.json()) as Record<string, any>;
  }

  return {
    getSubscription: (id) => get(`subscriptions/${encodeURIComponent(id)}`),
    getCheckoutLineItems: async (sessionId) => {
      const data = await get(`checkout/sessions/${encodeURIComponent(sessionId)}/line_items?limit=10`);
      return Array.isArray(data.data) ? data.data : [];
    },
    getInvoices: async (customerId) => {
      const data = await get(`invoices?customer=${encodeURIComponent(customerId)}&limit=10`);
      return Array.isArray(data.data) ? data.data : [];
    },
    createBillingPortalSession: async (customerId, returnUrl) => {
      const data = await postForm("billing_portal/sessions", { customer: customerId, return_url: returnUrl });
      if (typeof data.url !== "string" || !data.url) throw new Error("Stripe did not return a billing portal URL");
      return data.url;
    },
    createAdditionalComputerCheckout: async (input) => {
      const values: Record<string, string> = {
        mode: "payment", customer: input.customerId, "metadata[customer_id]": input.customerId,
        "metadata[license_id]": input.licenseId, "metadata[quantity]": String(input.quantity),
        "metadata[product]": "LongJumpReplay", "metadata[purchase_type]": "additional_computers",
        success_url: input.successUrl, cancel_url: input.cancelUrl, client_reference_id: `longjumpreplay_addon_${crypto.randomUUID().replaceAll("-", "").slice(0, 8)}`,
      };
      input.pricesCzk.forEach((amount, index) => {
        values[`line_items[${index}][price_data][currency]`] = "czk";
        values[`line_items[${index}][price_data][unit_amount]`] = String(amount * 100);
        values[`line_items[${index}][price_data][product_data][name]`] = "LongJumpReplay — additional computer";
        values[`line_items[${index}][quantity]`] = "1";
      });
      const data = await postForm("checkout/sessions", values);
      if (typeof data.url !== "string" || !data.url) throw new Error("Stripe did not return a Checkout URL");
      return data.url;
    },
  };
}

/**
 * Stripe subscription statuses that should keep a licence usable.
 * `past_due` is included on purpose: a card that fails on Friday should not
 * disable the software at a Saturday competition. The grace period in
 * config.ts bounds how long that lasts.
 */
export const ACTIVE_SUBSCRIPTION_STATUSES = new Set(["active", "trialing", "past_due"]);
export const DEAD_SUBSCRIPTION_STATUSES = new Set(["canceled", "unpaid", "incomplete_expired"]);

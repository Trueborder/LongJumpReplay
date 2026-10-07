import { describe, expect, it, vi, afterEach } from "vitest";
import { longJumpReplayOrderConfirmationEmail } from "./email";
import { LJR_POLICY_VERSIONS, publicLjrOrder } from "./ljr-purchases";
import { stripeApi } from "./stripe";

describe("LongJumpReplay purchase compliance", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("uses versioned policy evidence and does not expose consent details in portal order data", () => {
    expect(LJR_POLICY_VERSIONS.purchase).toBe("2026-10-07");
    const result = publicLjrOrder({
      id: "ljr_order_test", customer_id: "cus_test", email: "buyer@example.com", product_id: "LongJumpReplay", stripe_product_id: "prod_test", stripe_price_id: "price_test", product_name: "LongJumpReplay", license_type: "lifetime", displayed_price_minor: 499000, currency: "czk", tax_notice: "pending", purchase_terms_version: LJR_POLICY_VERSIONS.purchase, eula_version: LJR_POLICY_VERSIONS.eula, refund_policy_version: LJR_POLICY_VERSIONS.refund, privacy_policy_version: LJR_POLICY_VERSIONS.privacy, consent_version: LJR_POLICY_VERSIONS.consent, terms_accepted_at: 1, immediate_delivery_requested_at: 1, withdrawal_acknowledged_at: 1, idempotency_key: "ljr_test_key", stripe_checkout_session_id: "cs_test", stripe_customer_id: "cus_test", payment_intent_id: "pi_test", stripe_subscription_id: null, license_id: "lic_test", status: "paid", delivery_status: "delivered", confirmation_status: "sent", receipt_reference: "pi_test", refund_status: null, dispute_status: null, entitlement_status: "active", paid_at: 2, created_at: 1, updated_at: 2,
    });
    expect(result.license_id).toBe("lic_test");
    expect(JSON.stringify(result)).not.toContain("buyer@example.com");
    expect(JSON.stringify(result)).not.toContain("terms_accepted_at");
  });

  it("passes only safe LongJumpReplay metadata to Stripe Checkout", async () => {
    let body = "";
    vi.stubGlobal("fetch", vi.fn(async (_url: string, init?: RequestInit) => { body = String(init?.body ?? ""); return Response.json({ id: "cs_test", url: "https://checkout.stripe.com/c/pay/test" }); }));
    const result = await stripeApi("sk_test_secret").createLongJumpReplayCheckout({ priceId: "price_lifetime", mode: "payment", email: "buyer@example.com", orderId: "ljr_order_test", licenseType: "lifetime", successUrl: "https://account.tomaspisar.cz/dashboard/billing", cancelUrl: "https://account.tomaspisar.cz/checkout", policyVersions: LJR_POLICY_VERSIONS });
    expect(result.url).toContain("checkout.stripe.com");
    expect(body).toContain("metadata%5Bpurchase_type%5D=longjumpreplay_license");
    expect(body).toContain("metadata%5Border_id%5D=ljr_order_test");
    expect(body).not.toContain("sk_test_secret");
  });

  it("creates a durable confirmation with order, licence and policy links", () => {
    const message = longJumpReplayOrderConfirmationEmail({ orderId: "ljr_order_test", productName: "LongJumpReplay", licenseType: "lifetime", priceMinor: 499000, currency: "czk", paidAt: 1, deliveryUrl: "https://account.tomaspisar.cz/dashboard/billing", purchaseUrl: "https://tomaspisar.cz/legal/longjumpreplay-purchases/", eulaUrl: "https://tomaspisar.cz/legal/longjumpreplay-eula/", refundUrl: "https://tomaspisar.cz/legal/longjumpreplay-refunds/", privacyUrl: "https://tomaspisar.cz/products/long-jump-replay/privacy/", supportEmail: "info@tomaspisar.cz" });
    expect(message.text).toContain("ljr_order_test");
    expect(message.text).toContain("longjumpreplay-eula");
    expect(message.html).toContain("longjumpreplay-refunds");
  });
});

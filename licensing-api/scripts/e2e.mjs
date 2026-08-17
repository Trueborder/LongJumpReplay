/**
 * End-to-end test against a locally running Worker (`wrangler dev --local`)
 * with real D1. Covers the flows §27 asks for.
 *
 * The verification code is never returned by the API, so the test recovers it
 * the same way an attacker with database access would have to - by brute
 * forcing the HMAC over the 10^6 possible codes using the local pepper. That
 * keeps the production code free of any test-only backdoor, and incidentally
 * demonstrates why the pepper matters.
 *
 *   node scripts/e2e.mjs http://127.0.0.1:8787
 */
import { readFileSync } from "node:fs";
import { createHmac } from "node:crypto";
import { DatabaseSync } from "node:sqlite";
import { readdirSync } from "node:fs";
import { join } from "node:path";

const BASE = process.argv[2] ?? "http://127.0.0.1:8787";

const devVars = Object.fromEntries(
  readFileSync(".dev.vars", "utf8")
    .split("\n")
    .filter((l) => l && !l.startsWith("#"))
    .map((l) => {
      const i = l.indexOf("=");
      return [l.slice(0, i), l.slice(i + 1)];
    }),
);
const WEBHOOK_SECRET = devVars.STRIPE_WEBHOOK_SECRET;
const PEPPER = devVars.VERIFICATION_PEPPER;

let passed = 0;
let failed = 0;
function check(name, condition, detail = "") {
  if (condition) {
    passed += 1;
    console.log(`  PASS  ${name}`);
  } else {
    failed += 1;
    console.log(`  FAIL  ${name}${detail ? "  <- " + detail : ""}`);
  }
}

async function post(path, body, headers = {}) {
  const payload = typeof body === "string" ? body : JSON.stringify(body);
  const response = await fetch(BASE + path, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body: payload,
  });
  let json = null;
  try {
    json = await response.json();
  } catch {
    /* empty body */
  }
  return { status: response.status, json };
}

function stripeHeaders(payload, secret = WEBHOOK_SECRET, timestamp = Math.floor(Date.now() / 1000)) {
  const signature = createHmac("sha256", secret).update(`${timestamp}.${payload}`).digest("hex");
  return { "Stripe-Signature": `t=${timestamp},v1=${signature}` };
}

function checkoutEvent(id, email, mode, subscriptionId = null) {
  return {
    id,
    type: "checkout.session.completed",
    data: {
      object: {
        id: `cs_${id}`,
        mode,
        customer: `cus_${id}`,
        subscription: subscriptionId,
        customer_details: { email, name: "Test Buyer" },
      },
    },
  };
}

/** Recover the code by brute force over the local pepper. */
function findLocalD1File() {
  const root = join(".wrangler", "state", "v3", "d1", "miniflare-D1DatabaseObject");
  const files = readdirSync(root).filter((f) => f.endsWith(".sqlite"));
  return join(root, files[0]);
}

function recoverCode(email) {
  const db = new DatabaseSync(findLocalD1File(), { readOnly: true });
  const row = db
    .prepare(
      "SELECT code_hash FROM verification_codes WHERE email = ? AND used_at IS NULL ORDER BY created_at DESC LIMIT 1",
    )
    .get(email);
  db.close();
  if (!row) return null;
  for (let i = 0; i < 1_000_000; i += 1) {
    const candidate = String(i).padStart(6, "0");
    const mac = createHmac("sha256", PEPPER).update(candidate).digest("base64url");
    if (mac === row.code_hash) return candidate;
  }
  return null;
}

const MACHINE_A = "bWFjaGluZUFhYWFhYWFhYWFhYWFh";
const MACHINE_B = "bWFjaGluZUJiYmJiYmJiYmJiYmJi";
const MACHINE_C = "bWFjaGluZUNjY2NjY2NjY2NjY2Nj";

console.log("\n== health ==");
{
  const response = await fetch(BASE + "/health");
  check("health responds 200", response.status === 200);
}

console.log("\n== webhook security ==");
{
  const event = checkoutEvent("evt_sec", "sec@example.com", "payment");
  const payload = JSON.stringify(event);

  const forged = await post("/api/stripe/webhook", payload, stripeHeaders(payload, "whsec_wrong"));
  check("forged signature rejected", forged.status === 400, `got ${forged.status}`);

  const unsigned = await post("/api/stripe/webhook", payload);
  check("unsigned request rejected", unsigned.status === 400, `got ${unsigned.status}`);

  const stale = await post(
    "/api/stripe/webhook",
    payload,
    stripeHeaders(payload, WEBHOOK_SECRET, Math.floor(Date.now() / 1000) - 3600),
  );
  check("stale timestamp rejected", stale.status === 400, `got ${stale.status}`);

  const tampered = payload.replace("sec@example.com", "thief@example.com");
  const tamperedResponse = await post("/api/stripe/webhook", tampered, stripeHeaders(payload));
  check("tampered body rejected", tamperedResponse.status === 400, `got ${tamperedResponse.status}`);
}

console.log("\n== lifetime purchase ==");
const lifetimeEmail = `life${Date.now()}@example.com`;
{
  const event = checkoutEvent("evt_life_" + Date.now(), lifetimeEmail, "payment");
  const payload = JSON.stringify(event);
  const first = await post("/api/stripe/webhook", payload, stripeHeaders(payload));
  check("lifetime webhook accepted", first.status === 200, JSON.stringify(first.json));

  const duplicate = await post("/api/stripe/webhook", payload, stripeHeaders(payload));
  check("duplicate event is idempotent", duplicate.json?.duplicate === event.id, JSON.stringify(duplicate.json));
}

console.log("\n== activation ==");
let grant = null;
{
  const requested = await post("/api/license/request-code", { email: lifetimeEmail });
  // Mail is unconfigured locally, so sending fails after the code row is written.
  check("code requested (send fails locally as expected)", requested.status === 502 || requested.status === 200, `got ${requested.status}`);

  const unknown = await post("/api/license/request-code", { email: "nobody@example.com" });
  check("unknown email gives identical generic response", unknown.status === 200 && unknown.json?.sent === true);

  const code = recoverCode(lifetimeEmail);
  check("verification code was stored hashed", code !== null);

  const wrong = await post("/api/license/verify-code", {
    email: lifetimeEmail,
    code: code === "000000" ? "111111" : "000000",
  });
  check("wrong code rejected", wrong.status === 400, `got ${wrong.status}`);

  const verified = await post("/api/license/verify-code", { email: lifetimeEmail, code });
  check("correct code accepted", verified.json?.verified === true, JSON.stringify(verified.json));
  grant = verified.json?.activation_grant ?? null;
  check("activation grant issued", typeof grant === "string" && grant.length > 20);
}

console.log("\n== device limit ==");
{
  const a = await post("/api/license/activate", { activation_grant: grant, machine_id: MACHINE_A });
  check("device 1 activates", a.json?.activated === true, JSON.stringify(a.json));
  check("authorization returned", typeof a.json?.authorization === "string" && a.json.authorization.startsWith("LJRA1."));
  check("license type is lifetime", a.json?.license_type === "lifetime");

  const replay = await post("/api/license/activate", { activation_grant: grant, machine_id: MACHINE_B });
  check("grant is single use", replay.status === 401, `got ${replay.status}`);

  // Second device needs a fresh verification round.
  await post("/api/license/request-code", { email: lifetimeEmail });
  const code2 = recoverCode(lifetimeEmail);
  const verified2 = await post("/api/license/verify-code", { email: lifetimeEmail, code: code2 });
  const b = await post("/api/license/activate", {
    activation_grant: verified2.json.activation_grant,
    machine_id: MACHINE_B,
  });
  check("device 2 activates", b.json?.activated === true, JSON.stringify(b.json));

  await post("/api/license/request-code", { email: lifetimeEmail });
  const code3 = recoverCode(lifetimeEmail);
  const verified3 = await post("/api/license/verify-code", { email: lifetimeEmail, code: code3 });
  const c = await post("/api/license/activate", {
    activation_grant: verified3.json.activation_grant,
    machine_id: MACHINE_C,
  });
  check("device 3 rejected at limit", c.status === 409 && c.json?.error === "device_limit", JSON.stringify(c.json));

  // Freeing a slot lets the third device on.
  await post("/api/license/request-code", { email: lifetimeEmail });
  const code4 = recoverCode(lifetimeEmail);
  const verified4 = await post("/api/license/verify-code", { email: lifetimeEmail, code: code4 });
  const removed = await post("/api/license/deactivate-device", {
    activation_grant: verified4.json.activation_grant,
    machine_id: MACHINE_A,
  });
  check("device 1 deactivates", removed.json?.deactivated === true, JSON.stringify(removed.json));

  await post("/api/license/request-code", { email: lifetimeEmail });
  const code5 = recoverCode(lifetimeEmail);
  const verified5 = await post("/api/license/verify-code", { email: lifetimeEmail, code: code5 });
  const cAgain = await post("/api/license/activate", {
    activation_grant: verified5.json.activation_grant,
    machine_id: MACHINE_C,
  });
  check("device 3 activates after a slot is freed", cAgain.json?.activated === true, JSON.stringify(cAgain.json));
}

console.log("\n== wrong email cannot activate ==");
{
  const other = await post("/api/license/request-code", { email: `other${Date.now()}@example.com` });
  check("unknown email still returns generic success", other.json?.sent === true);
  const code = recoverCode(lifetimeEmail);
  const cross = await post("/api/license/verify-code", { email: `other${Date.now()}@example.com`, code });
  check("code from another account rejected", cross.status === 400, `got ${cross.status}`);
}

console.log("\n== subscription lifecycle ==");
const subEmail = `sub${Date.now()}@example.com`;
const subId = `sub_${Date.now()}`;
{
  const event = checkoutEvent("evt_sub_" + Date.now(), subEmail, "subscription", subId);
  const payload = JSON.stringify(event);
  const created = await post("/api/stripe/webhook", payload, stripeHeaders(payload));
  check("subscription webhook accepted", created.status === 200, JSON.stringify(created.json));

  await post("/api/license/request-code", { email: subEmail });
  const code = recoverCode(subEmail);
  const verified = await post("/api/license/verify-code", { email: subEmail, code });
  const activated = await post("/api/license/activate", {
    activation_grant: verified.json.activation_grant,
    machine_id: MACHINE_A,
  });
  check("subscription device activates", activated.json?.activated === true, JSON.stringify(activated.json));
  check("license type is subscription", activated.json?.license_type === "subscription");

  if (!activated.json?.authorization) {
    check("subscription authorization issued", false, JSON.stringify(activated.json));
    console.log(`\n${passed} passed, ${failed} failed`);
    process.exit(1);
  }
  const licenseId = JSON.parse(
    Buffer.from(activated.json.authorization.split(".")[1], "base64url").toString(),
  ).license_id;

  const refreshed = await post("/api/license/verify", { license_id: licenseId, machine_id: MACHINE_A });
  check("periodic verify refreshes authorization", refreshed.json?.valid === true, JSON.stringify(refreshed.json));

  // Cancel it in Stripe.
  const cancel = {
    id: "evt_cancel_" + Date.now(),
    type: "customer.subscription.deleted",
    data: { object: { id: subId, status: "canceled", current_period_end: Math.floor(Date.now() / 1000) } },
  };
  const cancelPayload = JSON.stringify(cancel);
  await post("/api/stripe/webhook", cancelPayload, stripeHeaders(cancelPayload));

  const afterCancel = await post("/api/license/verify", { license_id: licenseId, machine_id: MACHINE_A });
  check("cancelled subscription stops verifying", afterCancel.status === 403, `got ${afterCancel.status}`);

  const unknownDevice = await post("/api/license/verify", { license_id: licenseId, machine_id: MACHINE_C });
  check("unactivated device cannot verify", unknownDevice.status === 403, `got ${unknownDevice.status}`);
}

console.log("\n== input validation ==");
{
  const bad = await post("/api/license/request-code", { email: "not-an-email" });
  check("invalid email rejected", bad.status === 400);
  const badMachine = await post("/api/license/activate", { activation_grant: "x", machine_id: "short" });
  check("malformed machine id rejected", badMachine.status === 400);
  const notFound = await post("/api/license/nope", {});
  check("unknown route 404s", notFound.status === 404);
}

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);

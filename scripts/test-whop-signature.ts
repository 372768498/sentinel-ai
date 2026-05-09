import crypto from "node:crypto";

const secret = process.env.WHOP_WEBHOOK_SECRET ?? "";

if (!secret) {
  console.error("Missing WHOP_WEBHOOK_SECRET in env");
  process.exit(1);
}

const samplePayload = {
  action: "membership.went_valid",
  data: {
    id: "mem_test_123",
    product_id: process.env.WHOP_PRODUCT_ID_PRO ?? "prod_test",
    plan_id: process.env.WHOP_PLAN_ID_PRO ?? "plan_test",
    user: { id: "user_test", email: "test@example.com" },
    status: "active",
    valid: true,
    renewal_period_end: Math.floor(Date.now() / 1000) + 60 * 60 * 24 * 30
  }
};

const rawBody = JSON.stringify(samplePayload);
const signature = crypto.createHmac("sha256", secret).update(rawBody).digest("hex");

const target = process.argv[2] ?? "http://localhost:3000/api/webhooks/whop";

(async () => {
  const response = await fetch(target, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Whop-Signature": signature
    },
    body: rawBody
  });

  const text = await response.text();
  console.log(JSON.stringify(
    {
      target,
      status: response.status,
      signature,
      body: text
    },
    null,
    2
  ));
})();

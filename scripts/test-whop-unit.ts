import "dotenv/config";
import crypto from "node:crypto";

import { verifyWhopSignature } from "../lib/whop";
import { createVipInviteLink } from "../lib/telegram";

async function testSignature() {
  const secret = process.env.WHOP_WEBHOOK_SECRET;
  if (!secret) {
    console.log("[skip] signature test: WHOP_WEBHOOK_SECRET not set");
    return;
  }

  const body = JSON.stringify({ action: "membership.went_valid", data: { id: "mem_x" } });
  const goodSig = crypto.createHmac("sha256", secret).update(body).digest("hex");

  const okPlain = verifyWhopSignature(body, goodSig);
  const okSha256 = verifyWhopSignature(body, `sha256=${goodSig}`);
  const okV1 = verifyWhopSignature(body, `t=12345,v1=${goodSig}`);
  const badSig = verifyWhopSignature(body, "deadbeef".repeat(8));
  const emptySig = verifyWhopSignature(body, null);

  console.log("[signature]", {
    plain: okPlain,
    sha256_prefix: okSha256,
    stripe_style: okV1,
    bad_rejected: !badSig,
    empty_rejected: !emptySig
  });

  const allPass = okPlain && okSha256 && okV1 && !badSig && !emptySig;
  if (!allPass) {
    console.error("[signature] FAIL");
    process.exitCode = 1;
  } else {
    console.log("[signature] PASS");
  }
}

async function testTelegramInvite() {
  if (!process.env.TELEGRAM_BOT_TOKEN || !process.env.TELEGRAM_GROUP_ID_VIP) {
    console.log("[skip] telegram test: TELEGRAM_BOT_TOKEN or TELEGRAM_GROUP_ID_VIP not set");
    return;
  }

  try {
    const link = await createVipInviteLink({
      memberLimit: 1,
      name: `smoke-test-${Date.now()}`
    });
    console.log("[telegram] PASS — created invite link:", link.inviteLink);
  } catch (error) {
    console.error("[telegram] FAIL:", error instanceof Error ? error.message : error);
    process.exitCode = 1;
  }
}

(async () => {
  await testSignature();
  await testTelegramInvite();
})();

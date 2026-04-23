import crypto from "node:crypto";
import fs from "node:fs";

type ArgMap = Record<string, string>;

function parseArgs(argv: string[]) {
  return argv.reduce<ArgMap>((accumulator, current, index) => {
    if (!current.startsWith("--")) {
      return accumulator;
    }

    const key = current.slice(2);
    const next = argv[index + 1];
    if (!next || next.startsWith("--")) {
      accumulator[key] = "true";
      return accumulator;
    }

    accumulator[key] = next;
    return accumulator;
  }, {});
}

function usage() {
  console.error(
    "Usage: npx tsx scripts/verify-webhook-signature.ts --secret <secret> --signature <x-signature> --body-file <payload.json> [--mode live|test] [--test-mode true|false]"
  );
}

const args = parseArgs(process.argv.slice(2));
const secret = args.secret;
const signature = (args.signature ?? "").trim().toLowerCase();
const bodyFile = args["body-file"];
const expectedMode = (args.mode ?? "live").trim().toLowerCase();
const payloadTestMode = args["test-mode"];

if (!secret || !signature || !bodyFile) {
  usage();
  process.exit(1);
}

const rawBody = fs.readFileSync(bodyFile, "utf8");
const digest = crypto.createHmac("sha256", secret).update(rawBody).digest("hex").toLowerCase();
const verified = digest === signature;
const modeMatches =
  payloadTestMode === undefined
    ? "unknown"
    : expectedMode === "test"
      ? String(payloadTestMode).toLowerCase() === "true"
      : String(payloadTestMode).toLowerCase() === "false";

console.log(
  JSON.stringify(
    {
      verified,
      expectedMode,
      modeMatches,
      digest,
      signature
    },
    null,
    2
  )
);

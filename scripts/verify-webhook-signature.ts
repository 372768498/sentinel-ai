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
    "Usage: npx tsx scripts/verify-webhook-signature.ts --secret <secret> --signature <x-whop-signature> --body-file <payload.json>"
  );
}

const args = parseArgs(process.argv.slice(2));
const secret = args.secret;
const signature = (args.signature ?? "").trim().toLowerCase();
const bodyFile = args["body-file"];

if (!secret || !signature || !bodyFile) {
  usage();
  process.exit(1);
}

const rawBody = fs.readFileSync(bodyFile, "utf8");
const digest = crypto.createHmac("sha256", secret).update(rawBody).digest("hex").toLowerCase();
const verified = digest === signature;

console.log(
  JSON.stringify(
    {
      verified,
      digest,
      signature
    },
    null,
    2
  )
);

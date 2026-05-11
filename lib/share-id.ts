import { randomBytes } from "crypto";

export function generateShareId(): string {
  return randomBytes(8).toString("hex");
}

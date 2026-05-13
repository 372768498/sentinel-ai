# Resend Sending Domain — `mail.jilo.ai`

> **Status (2026-05-13 09:55 ET)**: Verified. Magic-link / report emails ship
> with `From: Sentinel AI <noreply@mail.jilo.ai>` to any recipient.
> Region: `us-east-1`. DNS host: DNSowl (apex `jilo.ai`).

## 1. Why a dedicated sub-domain

Resend (Amazon SES backend) requires a verified domain before it will deliver
to non-sandbox recipients. We verify the **sub-domain** `mail.jilo.ai` instead
of the apex `jilo.ai` so:

- Resend never touches the apex MX (Whop / website mail untouched).
- DKIM key rotation stays scoped to the sub-domain.
- Reputation incidents on transactional mail don't bleed into the apex.

## 2. The four DNS records

All records live under apex `jilo.ai` in DNSowl. Names below are the **host
part only** (DNSowl auto-appends the apex).

### 2.1 SPF — TXT on `send.mail`

| Field | Value |
| --- | --- |
| Type | `TXT` |
| Host | `send.mail` |
| Value | `v=spf1 include:amazonses.com ~all` |
| TTL | default |

Authorises Amazon SES to send on behalf of `send.mail.jilo.ai`. Required even
though we set `RESEND_FROM_EMAIL=noreply@mail.jilo.ai` — Resend rewrites the
SMTP `MAIL FROM` to a `send.mail.jilo.ai` bounce address for SPF alignment.

### 2.2 DKIM — TXT on `resend._domainkey.mail`

| Field | Value |
| --- | --- |
| Type | `TXT` |
| Host | `resend._domainkey.mail` |
| Value | single 218-char string starting `p=MIGfMA0...` ending `...AQAB` (see Resend dashboard for the exact key) |
| TTL | default |

> **Important — no whitespace in the DKIM value.** Paste the entire `p=...AQAB` blob as one continuous string. Most DNS providers split long TXT records into 255-char chunks under the hood, but the input we paste must contain **zero spaces or line breaks**. A single accidental newline (or a markdown editor that soft-wraps with a space) yields a record that round-trips through the DNS UI yet fails Resend verify.

### 2.3 MX — on `send.mail`

| Field | Value |
| --- | --- |
| Type | `MX` |
| Host | `send.mail` |
| Priority | `10` per Resend's template; DNS currently shows `0` and verifies fine |
| Value | `feedback-smtp.us-east-1.amazonses.com` |
| TTL | default |

Receives bounce / complaint feedback from SES. The region segment
(`us-east-1`) must match the Resend project region — if you ever move the
project to another region, this record needs to change.

### 2.4 DMARC — TXT on `_dmarc` (apex)

| Field | Value |
| --- | --- |
| Type | `TXT` |
| Host | `_dmarc` |
| Value | `v=DMARC1; p=none;` |
| TTL | default |

> **Known caveat**: the live record is on `_dmarc.jilo.ai` (apex), not on
> `_dmarc.mail.jilo.ai`. Resend's verify passes without the sub-domain DMARC
> because DKIM + SPF cover alignment. We can add a tighter
> `_dmarc.mail` record later if we move to `p=quarantine`; for now `p=none`
> on the apex is intentional.

## 3. Verify flow (next time we add a sender domain)

1. Resend dashboard → Domains → **Add domain** → enter `mail.jilo.ai` →
   pick region `us-east-1`.
2. Resend prints the four records above (the DKIM `p=` value is unique per
   project — copy the new one verbatim).
3. In DNSowl, add each record with the **host part** only (no trailing
   `.jilo.ai`).
4. Wait 1–5 min, then click **Verify** in the Resend dashboard. SES checks:
   - DKIM TXT record present + matches the key
   - SPF TXT record present
   - MX record points at `feedback-smtp.<region>.amazonses.com`
   - DMARC TXT record present (any value with `v=DMARC1` is enough)
5. All four flip to **Verified** within ~30 s of DNS propagation. Resend
   surfaces the per-record check on the domain detail page.

## 4. Switching `RESEND_FROM_EMAIL`

Once verified, set on both Vercel (Next.js) and Railway (worker):

```text
RESEND_FROM_EMAIL=Sentinel AI <noreply@mail.jilo.ai>
```

The local-part (`noreply`) is arbitrary — Resend accepts any mailbox under
the verified sub-domain. Pick a short, generic name; replies go nowhere
unless we add inbound forwarding (we don't).

After updating env on Vercel, run `vercel --prod --yes` so the new value
ships in the next build. Railway picks up the change on the next deploy
(or `railway redeploy --service sentinel-ai --yes` for an immediate restart).

## 5. Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `Resend error: 403 The 'from' address is not associated with a verified domain` | DKIM record contains whitespace; or region mismatch | Re-paste DKIM as one line; confirm Resend region matches the MX hostname |
| Email lands in spam | Recipient inbox doesn't yet trust the new domain | Warm up gradually; add DMARC reporting later; pre-warm by sending to a few real inboxes |
| `400 The api key is invalid` | Wrong Resend API key | Rotate via Resend dashboard, update Vercel + Railway env |
| Domain stuck at `Pending` for >10 min | DNS not propagated, or host appended apex twice (e.g. `send.mail.jilo.ai.jilo.ai`) | Re-check the host field; some providers want apex stripped |

## 6. Reference

- Resend dashboard: <https://resend.com/domains>
- Amazon SES DKIM docs: <https://docs.aws.amazon.com/ses/latest/dg/send-email-authentication-dkim.html>
- DMARC overview: <https://dmarc.org/overview/>

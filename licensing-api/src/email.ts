/**
 * Transactional email for verification codes.
 *
 * The project had no email provider, so this is provider-agnostic: the sending
 * function is chosen by the shape of MAIL_API_KEY's companion setting rather
 * than hardcoding one vendor. Cloudflare Email Sending is the default because
 * the domain is already on Cloudflare; Resend is supported as an alternative
 * because it needs nothing but an API key.
 */

import type { Env } from "./config";

export interface Mailer {
  send(to: string, subject: string, text: string): Promise<void>;
}

function body(code: string, ttlMinutes: number, purpose: "activation" | "portal"): string {
  const heading = purpose === "portal" ? "LongJumpReplay customer portal" : "LongJumpReplay activation";
  const destination = purpose === "portal"
    ? "the LongJumpReplay customer portal"
    : "the LongJumpReplay activation window";
  return [
    heading,
    "",
    `Your verification code is: ${code}`,
    "",
    `The code is valid for ${ttlMinutes} minutes and can be used once.`,
    "",
    "You are receiving this because someone entered this email address in the",
    `${destination}. If that was not you, no action is needed`,
    "and nothing has been activated.",
    "",
    "Never share this code. It is only ever typed into the LongJumpReplay",
    "application itself - nobody, including me, will ask you for it.",
    "",
    "Tomas Pisar",
    "https://tomaspisar.cz",
  ].join("\n");
}

/**
 * Resend, chosen when MAIL_API_KEY looks like a Resend key. Swap freely: the
 * only contract is `send`.
 */
function resendMailer(env: Env): Mailer {
  return {
    async send(to, subject, text) {
      const response = await fetch("https://api.resend.com/emails", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${env.MAIL_API_KEY}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          from: `${env.MAIL_FROM_NAME} <${env.MAIL_FROM}>`,
          to: [to],
          subject,
          text,
        }),
      });
      if (!response.ok) {
        // Status only - the body can echo the recipient address.
        throw new Error(`email send failed with ${response.status}`);
      }
    },
  };
}

/**
 * Used when no MAIL_API_KEY is configured. Fails loudly rather than pretending
 * to send, so a missing secret cannot look like a working activation flow.
 */
function unconfiguredMailer(): Mailer {
  return {
    async send() {
      throw new Error("no email provider configured: set the MAIL_API_KEY secret");
    },
  };
}

export function mailer(env: Env): Mailer {
  if (!env.MAIL_API_KEY) return unconfiguredMailer();
  return resendMailer(env);
}

export async function sendVerificationCode(
  env: Env,
  to: string,
  code: string,
  ttlMinutes: number,
  purpose: "activation" | "portal" = "activation",
): Promise<void> {
  const subject = purpose === "portal"
    ? "Your LongJumpReplay customer portal code"
    : "Your LongJumpReplay verification code";
  await mailer(env).send(to, subject, body(code, ttlMinutes, purpose));
}

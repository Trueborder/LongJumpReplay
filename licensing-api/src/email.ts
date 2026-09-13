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
  send(to: string, message: VerificationEmail): Promise<void>;
}

export interface VerificationEmail {
  subject: string;
  text: string;
  html: string;
  replyTo?: string;
}

export function verificationEmail(
  code: string,
  ttlMinutes: number,
  purpose: "activation" | "portal" | "password_reset" | "registration",
): VerificationEmail {
  const portal = purpose === "portal";
  const reset = purpose === "password_reset";
  const registration = purpose === "registration";
  const purposeLabel = reset ? "PASSWORD RESET" : registration ? "ACCOUNT REGISTRATION" : portal ? "CUSTOMER PORTAL LOGIN" : "APP ACTIVATION";
  const heading = reset ? "Reset your portal password" : registration ? "Verify your email address" : portal ? "Sign in to your account" : "Activate LongJumpReplay";
  const subject = reset
    ? "[LongJumpReplay] Customer portal password reset code"
    : registration
    ? "[LongJumpReplay] Account registration code"
    : portal
    ? "[LongJumpReplay] Customer portal login code"
    : "[LongJumpReplay] App activation code";
  const accent = reset || registration ? "#F3B84B" : portal ? "#F3B84B" : "#62D7C9";
  const destination = reset
    ? "the LongJumpReplay customer portal password reset"
    : registration
    ? "the LongJumpReplay customer portal registration"
    : purpose === "portal"
    ? "the LongJumpReplay customer portal"
    : "the LongJumpReplay activation window";
  const text = [
    `LONGJUMPREPLAY — ${purposeLabel}`,
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

  const html = `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${subject}</title></head>
<body style="margin:0;padding:0;background:#081012;color:#F4F1EA;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#081012;padding:28px 12px;">
    <tr><td align="center">
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:560px;background:#111B1F;border:1px solid #2B3A40;border-radius:20px;overflow:hidden;">
        <tr><td style="height:5px;background:${accent};font-size:0;line-height:0;">&nbsp;</td></tr>
        <tr><td style="padding:34px 34px 18px;">
          <div style="font:700 12px/1.4 ui-monospace,SFMono-Regular,Consolas,monospace;letter-spacing:1.5px;color:${accent};">${purposeLabel}</div>
          <h1 style="margin:13px 0 10px;font-size:30px;line-height:1.12;letter-spacing:-0.6px;color:#F4F1EA;">${heading}</h1>
          <p style="margin:0;color:#AAB7BC;font-size:16px;line-height:1.6;">Enter this one-time code in ${destination}.</p>
        </td></tr>
        <tr><td style="padding:8px 34px 24px;">
          <div style="background:#081012;border:1px solid ${accent};border-radius:14px;padding:22px;text-align:center;">
            <div style="margin-bottom:8px;font:700 11px/1.3 ui-monospace,SFMono-Regular,Consolas,monospace;letter-spacing:1.4px;color:#7F9097;">VERIFICATION CODE</div>
            <div style="font:800 36px/1.15 ui-monospace,SFMono-Regular,Consolas,monospace;letter-spacing:8px;color:${accent};">${code}</div>
          </div>
        </td></tr>
        <tr><td style="padding:0 34px 34px;">
          <p style="margin:0 0 14px;color:#D4DCDF;font-size:15px;line-height:1.6;">The code is valid for <strong>${ttlMinutes} minutes</strong> and can be used once.</p>
          <p style="margin:0 0 22px;color:#89999F;font-size:13px;line-height:1.6;">If you did not request this code, no action is needed. Nothing has been activated or signed in.</p>
          <div style="padding-top:18px;border-top:1px solid #2B3A40;color:#89999F;font-size:12px;line-height:1.6;">Never share this code. Type it only into LongJumpReplay or account.tomaspisar.cz.<br><strong style="color:#D4DCDF;">Tomáš Pisár</strong> · tomaspisar.cz</div>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>`;
  return { subject, text, html };
}

/**
 * Resend, chosen when MAIL_API_KEY looks like a Resend key. Swap freely: the
 * only contract is `send`.
 */
function resendMailer(env: Env): Mailer {
  return {
    async send(to, message) {
      const response = await fetch("https://api.resend.com/emails", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${env.MAIL_API_KEY}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          from: `${env.MAIL_FROM_NAME} <${env.MAIL_FROM}>`,
          to: [to],
          subject: message.subject,
          text: message.text,
          html: message.html,
          ...(message.replyTo ? { reply_to: message.replyTo } : {}),
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
  purpose: "activation" | "portal" | "password_reset" | "registration" = "activation",
): Promise<void> {
  await mailer(env).send(to, verificationEmail(code, ttlMinutes, purpose));
}

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[character] ?? character);
}

export function contactEmail(fields: { name: string; email: string; topic: string; message: string }): VerificationEmail {
  const subject = `[Website contact] ${fields.topic}`;
  const text = [
    "LongJumpReplay website contact form",
    `Name: ${fields.name}`,
    `Email: ${fields.email}`,
    `Topic: ${fields.topic}`,
    "",
    fields.message,
  ].join("\n");
  const html = `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>${escapeHtml(subject)}</title></head><body>
    <h1>Website contact form</h1>
    <p><strong>Name:</strong> ${escapeHtml(fields.name)}</p>
    <p><strong>Email:</strong> ${escapeHtml(fields.email)}</p>
    <p><strong>Topic:</strong> ${escapeHtml(fields.topic)}</p>
    <hr><p style="white-space:pre-wrap">${escapeHtml(fields.message)}</p>
  </body></html>`;
  return { subject, text, html, replyTo: fields.email };
}

export async function sendContactMessage(
  env: Env,
  fields: { name: string; email: string; topic: string; message: string },
): Promise<void> {
  await mailer(env).send("info@tomaspisar.cz", contactEmail(fields));
}

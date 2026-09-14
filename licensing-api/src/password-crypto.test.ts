import { describe, expect, it } from "vitest";
import { hashPassword, verifyPassword } from "./crypto";

describe("portal password hashing", () => {
  it("uses a salted, versioned PBKDF2 record and verifies only the right password", async () => {
    const first = await hashPassword("a sufficiently long passphrase");
    const second = await hashPassword("a sufficiently long passphrase");
    expect(first).toMatch(/^pbkdf2-sha256\$v1\$100000\$/);
    expect(first).not.toBe(second);
    await expect(verifyPassword("a sufficiently long passphrase", first)).resolves.toBe(true);
    await expect(verifyPassword("a different passphrase", first)).resolves.toBe(false);
  }, 15_000);

  it("rejects malformed or unsupported records", async () => {
    await expect(verifyPassword("a sufficiently long passphrase", "argon2$v1$1$salt$key")).resolves.toBe(false);
    await expect(verifyPassword("a sufficiently long passphrase", "pbkdf2-sha256$v2$600000$c2FsdA$key")).resolves.toBe(false);
  });
});

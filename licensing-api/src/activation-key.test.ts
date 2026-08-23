import { describe, expect, it } from "vitest";
import { decryptActivationKey, encryptActivationKey, generateActivationKey, normalizeActivationKey } from "./crypto";

describe("portal activation keys", () => {
  it("generates the exact human-friendly 4-4-4 format", () => {
    for (let index = 0; index < 100; index += 1) {
      expect(generateActivationKey()).toMatch(/^\d{4}-[A-HJ-NP-Z]{4}-[2-9A-HJ-NP-Z]{4}$/);
    }
  });

  it("normalises typed separators but rejects ambiguous or malformed keys", () => {
    expect(normalizeActivationKey("1234 abcd 2efg")).toBe("1234-ABCD-2EFG");
    expect(normalizeActivationKey("1234-ABIO-2EFG")).toBeNull();
    expect(normalizeActivationKey("1234-ABCD-0EFG")).toBeNull();
  });

  it("encrypts for reveal without storing plaintext", async () => {
    const key = "1234-ABCD-2EFG";
    const encrypted = await encryptActivationKey("test secret distinct from production", key);
    expect(encrypted.ciphertext).not.toContain(key);
    expect(await decryptActivationKey("test secret distinct from production", encrypted.ciphertext, encrypted.nonce)).toBe(key);
    await expect(decryptActivationKey("wrong secret", encrypted.ciphertext, encrypted.nonce)).rejects.toThrow();
  });
});

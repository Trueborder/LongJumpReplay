import { describe, expect, it } from "vitest";
import { buildPairingPortalUrl } from "./index";

describe("portal pairing QR links", () => {
  it("puts only the opaque token in the activation fragment", () => {
    const url = buildPairingPortalUrl("https://account.example.com", "token_abc-123");
    expect(url).toBe("https://account.example.com/dashboard/activation#pair=token_abc-123");
    expect(new URL(url).search).toBe("");
    expect(new URL(url).hash).toBe("#pair=token_abc-123");
  });
});

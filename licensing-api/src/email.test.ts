import { describe, expect, it } from "vitest";
import { verificationEmail } from "./email";

describe("verification email presentation", () => {
  it("makes app activation unmistakable in HTML and plain text", () => {
    const message = verificationEmail("123456", 10, "activation");
    expect(message.subject).toContain("App activation");
    expect(message.text).toContain("APP ACTIVATION");
    expect(message.html).toContain("APP ACTIVATION");
    expect(message.html).toContain("#62D7C9");
    expect(message.html).toContain("123456");
  });

  it("uses a distinct portal-login label and accent", () => {
    const message = verificationEmail("654321", 10, "portal");
    expect(message.subject).toContain("Customer portal login");
    expect(message.text).toContain("CUSTOMER PORTAL LOGIN");
    expect(message.html).toContain("CUSTOMER PORTAL LOGIN");
    expect(message.html).toContain("#F3B84B");
  });

  it("labels registration codes separately from login and activation", () => {
    const message = verificationEmail("111222", 10, "registration");
    expect(message.subject).toContain("Account registration");
    expect(message.text).toContain("ACCOUNT REGISTRATION");
    expect(message.html).toContain("ACCOUNT REGISTRATION");
  });
});

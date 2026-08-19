import { describe, expect, it } from "vitest";
import { portalPageRoute } from "./portal-routing";

describe("customer portal page routing", () => {
  it("sends the account root to the correct first screen", () => {
    expect(portalPageRoute("/", false)).toEqual({ kind: "redirect", location: "/login" });
    expect(portalPageRoute("/", true)).toEqual({ kind: "redirect", location: "/dashboard" });
  });

  it("keeps authenticated customers out of the login screen", () => {
    expect(portalPageRoute("/login", true)).toEqual({ kind: "redirect", location: "/dashboard" });
    expect(portalPageRoute("/login", false)).toEqual({ kind: "asset", assetPath: "/login/" });
  });

  it("protects the dashboard and canonicalizes trailing slashes", () => {
    expect(portalPageRoute("/dashboard", false)).toEqual({ kind: "redirect", location: "/login" });
    expect(portalPageRoute("/dashboard", true)).toEqual({ kind: "asset", assetPath: "/dashboard/" });
    expect(portalPageRoute("/login/", false)).toEqual({ kind: "redirect", location: "/login" });
    expect(portalPageRoute("/dashboard/", true)).toEqual({ kind: "redirect", location: "/dashboard" });
  });

  it("leaves scripts, styles, and other static assets to the asset binding", () => {
    expect(portalPageRoute("/account.js", false)).toBeNull();
  });
});

import { describe, expect, it } from "vitest";
import { portalPageRoute } from "./portal-routing";

describe("customer portal page routing", () => {
  it("sends the account root to the correct first screen", () => {
    expect(portalPageRoute("/", false)).toEqual({ kind: "redirect", location: "/login" });
    expect(portalPageRoute("/", true)).toEqual({ kind: "redirect", location: "/dashboard/overview" });
  });

  it("keeps authenticated customers out of the login screen", () => {
    expect(portalPageRoute("/login", true)).toEqual({ kind: "redirect", location: "/dashboard/overview" });
    expect(portalPageRoute("/login", false)).toEqual({ kind: "asset", assetPath: "/login/" });
  });

  it("protects the dashboard root and sends it to overview", () => {
    expect(portalPageRoute("/dashboard", false)).toEqual({ kind: "redirect", location: "/login" });
    expect(portalPageRoute("/dashboard", true)).toEqual({ kind: "redirect", location: "/dashboard/overview" });
    expect(portalPageRoute("/login/", false)).toEqual({ kind: "redirect", location: "/login" });
    expect(portalPageRoute("/dashboard/", true)).toEqual({ kind: "redirect", location: "/dashboard/overview" });
  });

  it("serves the standalone QR approval shell without exposing the dashboard", () => {
    expect(portalPageRoute("/approve/pairing", false)).toEqual({ kind: "asset", assetPath: "/approve/pairing/" });
    expect(portalPageRoute("/approve/pairing", true)).toEqual({ kind: "asset", assetPath: "/approve/pairing/" });
    expect(portalPageRoute("/approve/pairing/", false)).toEqual({ kind: "redirect", location: "/approve/pairing" });
  });

  it("serves every dashboard category at its own protected URL", () => {
    for (const category of ["overview", "licence", "activation-key", "activation", "devices", "billing", "help"]) {
      const unauthenticated = category === "activation"
        ? { kind: "asset", assetPath: "/dashboard/" }
        : { kind: "redirect", location: "/login" };
      expect(portalPageRoute(`/dashboard/${category}`, false)).toEqual(unauthenticated);
      expect(portalPageRoute(`/dashboard/${category}`, true)).toEqual({ kind: "asset", assetPath: "/dashboard/" });
      expect(portalPageRoute(`/dashboard/${category}/`, true)).toEqual({ kind: "redirect", location: `/dashboard/${category}` });
    }
  });

  it("does not turn unknown dashboard paths into account pages", () => {
    expect(portalPageRoute("/dashboard/unknown", true)).toBeNull();
  });

  it("leaves scripts, styles, and other static assets to the asset binding", () => {
    expect(portalPageRoute("/account.js", false)).toBeNull();
  });
});

export type PortalPageRoute =
  | { kind: "asset"; assetPath: string }
  | { kind: "redirect"; location: string }
  | null;

export const DASHBOARD_ROUTES = [
  "overview",
  "licence",
  "activation-key",
  "activation",
  "devices",
  "billing",
  "help",
] as const;

export const PAIRING_APPROVAL_ASSET = "/approve/pairing/";
export const REGISTRATION_ASSET = "/register/";

const dashboardPath = (path: string): boolean => {
  const match = path.match(/^\/dashboard\/([^/]+)\/?$/);
  return Boolean(match && DASHBOARD_ROUTES.includes(match[1] as (typeof DASHBOARD_ROUTES)[number]));
};

/** Resolve the public portal URLs while keeping auth policy out of asset code. */
export function portalPageRoute(path: string, authenticated: boolean, setupRequired = false): PortalPageRoute {
  if (path === "/") {
    return { kind: "redirect", location: authenticated ? (setupRequired ? "/register?mode=migration" : "/dashboard/overview") : "/login" };
  }
  if (path === "/register/") return { kind: "redirect", location: "/register" };
  if (path === "/register") return { kind: "asset", assetPath: REGISTRATION_ASSET };
  if (path === "/login/") return { kind: "redirect", location: "/login" };
  if (path === "/dashboard" || path === "/dashboard/") {
    return authenticated
      ? { kind: "redirect", location: setupRequired ? "/register?mode=migration" : "/dashboard/overview" }
      : { kind: "redirect", location: "/login" };
  }
  if (path === "/login") {
    return authenticated && !setupRequired
      ? { kind: "redirect", location: "/dashboard/overview" }
      : { kind: "asset", assetPath: "/login/" };
  }
  if (path === "/approve/pairing/") return { kind: "redirect", location: "/approve/pairing" };
  if (path === "/approve/pairing") return { kind: "asset", assetPath: PAIRING_APPROVAL_ASSET };
  // The activation shell must be reachable before login so a QR fragment can
  // be captured by the browser. Its account data and all mutations still go
  // through authenticated API calls from the page.
  if (path === "/dashboard/activation") return { kind: "asset", assetPath: "/dashboard/" };
  if (dashboardPath(path)) {
    if (path.endsWith("/")) return { kind: "redirect", location: path.slice(0, -1) };
    return authenticated
      ? (setupRequired ? { kind: "redirect", location: "/register?mode=migration" } : { kind: "asset", assetPath: "/dashboard/" })
      : { kind: "redirect", location: "/login" };
  }
  return null;
}

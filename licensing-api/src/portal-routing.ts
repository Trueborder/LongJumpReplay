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

const dashboardPath = (path: string): boolean => {
  const match = path.match(/^\/dashboard\/([^/]+)\/?$/);
  return Boolean(match && DASHBOARD_ROUTES.includes(match[1] as (typeof DASHBOARD_ROUTES)[number]));
};

/** Resolve the public portal URLs while keeping auth policy out of asset code. */
export function portalPageRoute(path: string, authenticated: boolean): PortalPageRoute {
  if (path === "/") {
    return { kind: "redirect", location: authenticated ? "/dashboard/overview" : "/login" };
  }
  if (path === "/login/") return { kind: "redirect", location: "/login" };
  if (path === "/dashboard" || path === "/dashboard/") {
    return authenticated
      ? { kind: "redirect", location: "/dashboard/overview" }
      : { kind: "redirect", location: "/login" };
  }
  if (path === "/login") {
    return authenticated
      ? { kind: "redirect", location: "/dashboard/overview" }
      : { kind: "asset", assetPath: "/login/" };
  }
  if (dashboardPath(path)) {
    if (path.endsWith("/")) return { kind: "redirect", location: path.slice(0, -1) };
    return authenticated
      ? { kind: "asset", assetPath: "/dashboard/" }
      : { kind: "redirect", location: "/login" };
  }
  return null;
}

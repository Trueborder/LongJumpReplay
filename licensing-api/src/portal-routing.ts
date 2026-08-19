export type PortalPageRoute =
  | { kind: "asset"; assetPath: string }
  | { kind: "redirect"; location: string }
  | null;

/** Resolve the public portal URLs while keeping auth policy out of asset code. */
export function portalPageRoute(path: string, authenticated: boolean): PortalPageRoute {
  if (path === "/") {
    return { kind: "redirect", location: authenticated ? "/dashboard" : "/login" };
  }
  if (path === "/login/") return { kind: "redirect", location: "/login" };
  if (path === "/dashboard/") return { kind: "redirect", location: "/dashboard" };
  if (path === "/login") {
    return authenticated
      ? { kind: "redirect", location: "/dashboard" }
      : { kind: "asset", assetPath: "/login/" };
  }
  if (path === "/dashboard") {
    return authenticated
      ? { kind: "asset", assetPath: "/dashboard/" }
      : { kind: "redirect", location: "/login" };
  }
  return null;
}

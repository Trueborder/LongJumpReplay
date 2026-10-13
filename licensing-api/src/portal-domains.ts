import type { Env } from './config';

export const LJR_ORIGIN = 'https://ljr.tomaspisar.cz';
export const MINECRAFT_ORIGIN = 'https://account.pantheon.tomaspisar.cz';
export const LEGACY_MINECRAFT_HOST = 'minecraft.tomaspisar.cz';
export function isMinecraftHost(host: string): boolean {
  return host === new URL(MINECRAFT_ORIGIN).hostname || host === LEGACY_MINECRAFT_HOST;
}

/** Redirect web pages, but never redirect signed bridge or payment POST requests. */
export function legacyMinecraftLocation(request: Request): string | null {
  const url = new URL(request.url);
  if (url.hostname !== LEGACY_MINECRAFT_HOST || url.pathname.startsWith('/api/')) return null;
  url.host = new URL(MINECRAFT_ORIGIN).host;
  return url.toString();
}
export type PortalProduct = 'economysuite' | 'longjumpreplay';
export const AUTH_PATHS = new Set([
  '/api/portal/account', '/api/portal/request-code', '/api/portal/verify-code',
  '/api/portal/register/request-code', '/api/portal/register/verify-code', '/api/portal/register/complete',
  '/api/portal/password/login', '/api/portal/password/enroll', '/api/portal/password/change',
  '/api/portal/password/reset/request', '/api/portal/password/reset', '/api/portal/logout',
  '/api/portal/data-export', '/api/portal/account/deletion-request',
]);

/** Origin/host determines the account boundary. Body/query product selectors cannot cross it. */
export function requestProduct(request: Request, env: Env): PortalProduct {
  const url = new URL(request.url);
  if (isMinecraftHost(url.hostname)) return 'economysuite';
  if (url.hostname === 'ljr.tomaspisar.cz') return 'longjumpreplay';
  if (url.pathname.startsWith('/api/economysuite/')) return 'economysuite';
  if (url.hostname === 'api.tomaspisar.cz' && request.headers.get('Origin') === (env.ECONOMYSUITE_PORTAL_ORIGIN || MINECRAFT_ORIGIN)) return 'economysuite';
  if (env.ENVIRONMENT !== 'production' && url.origin === env.ECONOMYSUITE_PORTAL_ORIGIN) return 'economysuite';
  return 'longjumpreplay';
}

export function accountEnv(env: Env, product: PortalProduct): Env {
  if (product === 'economysuite') {
    if (!env.ECONOMYSUITE_DB) throw new Error('Minecraft account database is not configured');
    return { ...env, DB: env.ECONOMYSUITE_DB, PORTAL_ORIGIN: env.ECONOMYSUITE_PORTAL_ORIGIN || MINECRAFT_ORIGIN, PORTAL_PRODUCT: product };
  }
  return { ...env, PORTAL_PRODUCT: product };
}

export function sessionCookieName(env: Env): string {
  return env.PORTAL_PRODUCT === 'economysuite' ? '__Host-es-session' : '__Host-ljr-session';
}
export function csrfCookieName(env: Env): string {
  return env.PORTAL_PRODUCT === 'economysuite' ? '__Host-es-csrf' : '__Host-ljr-csrf';
}

export function retiredAccountLocation(request: Request): string {
  const url = new URL(request.url);
  const minecraft = url.pathname.startsWith('/economysuite') || url.searchParams.get('product') === 'economysuite' || (url.searchParams.get('next') || '').startsWith('/economysuite/');
  url.host = new URL(minecraft ? MINECRAFT_ORIGIN : LJR_ORIGIN).host;
  url.searchParams.delete('product');
  return url.toString();
}

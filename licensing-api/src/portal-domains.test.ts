import { describe, expect, it } from 'vitest';
import { requestProduct, retiredAccountLocation, sessionCookieName, csrfCookieName } from './portal-domains';
import type { Env } from './config';

describe('product account boundaries', () => {
  const env = { ENVIRONMENT: 'production', PORTAL_ORIGIN: 'https://ljr.tomaspisar.cz', ECONOMYSUITE_PORTAL_ORIGIN: 'https://minecraft.tomaspisar.cz' } as Env;
  it('selects the host rather than an untrusted product selector', () => {
    expect(requestProduct(new Request('https://ljr.tomaspisar.cz/login?product=economysuite'), env)).toBe('longjumpreplay');
    expect(requestProduct(new Request('https://minecraft.tomaspisar.cz/login?product=longjumpreplay'), env)).toBe('economysuite');
    expect(requestProduct(new Request('https://api.tomaspisar.cz/api/portal/account', { headers: { Origin: 'https://minecraft.tomaspisar.cz' } }), env)).toBe('economysuite');
  });
  it('uses distinct host-only session and CSRF cookie names', () => {
    expect(sessionCookieName(env)).toBe('__Host-ljr-session');
    expect(csrfCookieName(env)).toBe('__Host-ljr-csrf');
    expect(sessionCookieName({ ...env, PORTAL_PRODUCT: 'economysuite' })).toBe('__Host-es-session');
    expect(csrfCookieName({ ...env, PORTAL_PRODUCT: 'economysuite' })).toBe('__Host-es-csrf');
  });
  it('retires old account links to the matching product while preserving pairing destinations', () => {
    expect(retiredAccountLocation(new Request('https://account.tomaspisar.cz/login?product=economysuite&next=/economysuite/pair'))).toBe('https://minecraft.tomaspisar.cz/login?next=%2Feconomysuite%2Fpair');
    expect(retiredAccountLocation(new Request('https://account.tomaspisar.cz/dashboard/licence'))).toBe('https://ljr.tomaspisar.cz/dashboard/licence');
  });
});

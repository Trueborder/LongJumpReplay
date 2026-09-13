interface SiteEnv {
  ASSETS: Fetcher;
}

const SWIMMING_API = 'https://vysledky.czechswimming.cz/cz.zma.csps.portal.rest/api/public';
const SWIMMING_ORIGIN = 'https://vysledky.czechswimming.cz';

const REDIRECTS: Record<string, string> = {
  '/download': '/products/long-jump-replay/download/',
  '/download/': '/products/long-jump-replay/download/',
  '/download/ljr': '/products/long-jump-replay/download/',
  '/download/ljr/': '/products/long-jump-replay/download/',
  '/licensing': '/products/long-jump-replay/licensing/',
  '/licensing/': '/products/long-jump-replay/licensing/',
  '/swimming/relaylab': '/products/relaylab/',
  '/swimming/relaylab/': '/products/relaylab/'
};

function legacyRouteRedirect(pathname: string): string | null {
  const migrations = [
    ['/software/longjumpreplay', '/products/long-jump-replay'],
    ['/software/relaylab', '/products/relaylab']
  ] as const;
  for (const [legacy, target] of migrations) {
    if (pathname === legacy || pathname === `${legacy}/`) return `${target}/`;
    if (pathname.startsWith(`${legacy}/`)) return `${target}${pathname.slice(legacy.length)}`;
  }
  if (pathname === '/software' || pathname === '/software/') return '/products/';
  if (pathname === '/privacy' || pathname === '/privacy/') return '/legal/privacy/';
  return null;
}

function json(data: unknown, status = 200, cache = 'no-store'): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      'content-type': 'application/json; charset=utf-8',
      'cache-control': cache,
      'x-content-type-options': 'nosniff'
    }
  });
}

function apiError(code: string, message: string, status: number): Response {
  return json({ error: { code, message } }, status);
}

async function upstream(path: string, cacheSeconds: number): Promise<Response> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 8000);
  try {
    const response = await fetch(`${SWIMMING_API}${path}`, {
      headers: { accept: 'application/json', 'user-agent': 'RelayLab/1.0 (+https://tomaspisar.cz)' },
      signal: controller.signal
    });
    if (!response.ok) return response;
    return new Response(response.body, {
      status: response.status,
      headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': `public, max-age=${cacheSeconds}` }
    });
  } finally {
    clearTimeout(timeout);
  }
}

async function handleSwimmingApi(request: Request, url: URL): Promise<Response> {
  if (request.method !== 'GET') return apiError('method_not_allowed', 'RelayLab data is read-only.', 405);

  const path = url.pathname;
  if (path === '/api/swimming/search') {
    const query = (url.searchParams.get('q') || '').trim();
    if (query.length < 2) return apiError('query_too_short', 'Type at least two characters to search.', 400);
    if (query.length > 80) return apiError('query_too_long', 'Search text is too long.', 400);
    try {
      const response = await upstream(`/search?query=${encodeURIComponent(query)}`, 600);
      if (!response.ok) return apiError('source_unavailable', 'The Czech Swimming search is temporarily unavailable.', 502);
      const source = await response.json() as Array<Record<string, unknown>>;
      const swimmers = source.slice(0, 12).flatMap((person) => {
        const id = Number(person.userId);
        if (!Number.isSafeInteger(id) || id <= 0) return [];
        return [{
          id,
          firstName: typeof person.firstName === 'string' ? person.firstName : '',
          lastName: typeof person.lastName === 'string' ? person.lastName : '',
          birthYear: Number.isInteger(person.birthYear) ? person.birthYear : null,
          clubAbbrev: typeof person.clubAbbrev === 'string' ? person.clubAbbrev : '',
          profileUrl: `${SWIMMING_ORIGIN}/lide/${id}`
        }];
      });
      return json({ swimmers }, 200, 'public, max-age=0, s-maxage=600');
    } catch (error) {
      return apiError(error instanceof DOMException && error.name === 'AbortError' ? 'source_timeout' : 'source_unavailable', 'The Czech Swimming search could not be reached. Try again or add the swimmer manually.', 502);
    }
  }

  const match = path.match(/^\/api\/swimming\/swimmers\/(\d+)\/times$/);
  if (!match) return apiError('not_found', 'RelayLab endpoint not found.', 404);
  const id = Number(match[1]);
  if (!Number.isSafeInteger(id) || id <= 0 || id > 999999999) return apiError('invalid_id', 'Enter a valid Czech Swimming swimmer ID.', 400);

  try {
    const [profileResponse, outputsResponse] = await Promise.all([
      upstream(`/user-profiles/${id}`, 900),
      upstream(`/user-profiles/${id}/outputs?mastersOnly=false`, 900)
    ]);
    if (profileResponse.status === 404 || outputsResponse.status === 404) return apiError('not_found', 'That swimmer was not found in the public Czech Swimming database.', 404);
    if (!profileResponse.ok || !outputsResponse.ok) return apiError('source_unavailable', 'The swimmer data is temporarily unavailable. You can still enter times manually.', 502);
    const profile = await profileResponse.json() as Record<string, unknown>;
    const outputs = await outputsResponse.json() as Array<Record<string, unknown>>;
    const member = (profile.userProfileClubMemberDto || {}) as Record<string, unknown>;
    const membershipHistory = Array.isArray(profile.membershipHistory) ? profile.membershipHistory as Array<Record<string, unknown>> : [];
    const latestMembership = membershipHistory[membershipHistory.length - 1] || {};
    const relevant = outputs.flatMap((output) => {
      const code = typeof output.disciplineCode === 'string' ? output.disciplineCode : '';
      const parsed = code.match(/^(50|100)\s+([ZPMK])$/);
      const timeMs = Number(output.time);
      const poolLength = Number(output.poolLength);
      if (!parsed || !Number.isFinite(timeMs) || timeMs <= 0 || ![25, 50].includes(poolLength)) return [];
      return [{
        distance: Number(parsed[1]),
        stroke: ({ Z: 'backstroke', P: 'breaststroke', M: 'butterfly', K: 'freestyle' } as Record<string, string>)[parsed[2]],
        disciplineCode: code,
        timeMs,
        poolLength,
        date: typeof output.date === 'string' ? output.date : null,
        venue: typeof output.competitionLocation === 'string' ? output.competitionLocation : '',
        relayPart: output.relayPart === true,
        splitTime: output.splitTime === true
      }];
    });
    return json({
      swimmer: {
        id,
        firstName: typeof profile.firstName === 'string' ? profile.firstName : '',
        lastName: typeof profile.lastName === 'string' ? profile.lastName : '',
        birthYear: Number.isInteger(profile.birthYear) ? profile.birthYear : null,
        sex: typeof profile.sex === 'string' ? profile.sex : null,
        clubName: typeof member.clubName === 'string' ? member.clubName : '',
        clubAbbrev: typeof member.clubAbbrev === 'string' ? member.clubAbbrev : (typeof latestMembership.clubAbbrev === 'string' ? latestMembership.clubAbbrev : ''),
        profileUrl: `${SWIMMING_ORIGIN}/lide/${id}`
      },
      performances: relevant,
      fetchedAt: new Date().toISOString()
    }, 200, 'public, max-age=0, s-maxage=900');
  } catch (error) {
    return apiError(error instanceof DOMException && error.name === 'AbortError' ? 'source_timeout' : 'source_unavailable', 'The swimmer data could not be reached. You can still enter times manually.', 502);
  }
}

export default {
  async fetch(request: Request, env: SiteEnv): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname.startsWith('/api/swimming/')) return handleSwimmingApi(request, url);
    const redirectTarget = legacyRouteRedirect(url.pathname) || REDIRECTS[url.pathname];
    if (redirectTarget) {
      const destination = new URL(redirectTarget, url.origin);
      destination.search = url.search;
      return new Response(null, { status: 301, headers: { location: destination.toString(), 'cache-control': 'public, max-age=3600' } });
    }
    return env.ASSETS.fetch(request);
  },
};

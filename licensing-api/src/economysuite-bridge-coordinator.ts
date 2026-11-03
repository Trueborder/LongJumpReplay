import type { Env } from './config';
import { economySuite } from './economysuite';

export const isCoordinatedBridgePoll = (path: string): boolean =>
  path === '/api/economysuite/bridge/poll' || path === '/api/economysuite/bridge/staff/poll';

const busy = () => Response.json({ error: 'bridge_busy', message: 'Bridge synchronization is busy. Retry shortly.' }, {
  status: 503, headers: { 'Cache-Control': 'no-store', 'Retry-After': '10' },
});

/** Transient scheduling only. Nonces, snapshots and operation receipts remain in D1. */
export class BridgePollQueue {
  private active = false;
  private waiting: Array<{ grant: () => void }> = [];

  constructor(private readonly maxWaiting = 8, private readonly waitMs = 5000) {}

  async run(task: () => Promise<Response>): Promise<Response> {
    if (this.active) {
      if (this.waiting.length >= this.maxWaiting) return busy();
      const acquired = await new Promise<boolean>(resolve => {
        const entry = { grant: () => { clearTimeout(timer); resolve(true); } };
        const timer = setTimeout(() => {
          this.waiting.splice(this.waiting.indexOf(entry), 1);
          resolve(false);
        }, this.waitMs);
        this.waiting.push(entry);
      });
      if (!acquired) return busy();
    } else this.active = true;
    try { return await task(); }
    finally {
      const next = this.waiting.shift();
      if (next) next.grant();
      else this.active = false;
    }
  }
}

/** One named object per game server, preserving the original signed HTTP envelope. */
export class EconomyBridgeCoordinator implements DurableObject {
  private readonly queue = new BridgePollQueue();

  constructor(_state: DurableObjectState, private readonly env: Env) {}

  async fetch(request: Request): Promise<Response> {
    const path = new URL(request.url).pathname;
    if (!isCoordinatedBridgePoll(path)) return new Response(null, { status: 404 });
    if (request.method !== 'POST') return new Response(null, { status: 405, headers: { Allow: 'POST' } });
    const response = await this.queue.run(() => economySuite(request, this.env, {
      // Only the signed bridge routes above are admitted; never authenticate portal users here.
      authenticate: async () => null,
      mutation: async () => false,
    }));
    const headers = new Headers(response.headers);
    headers.set('X-ES-Bridge-Execution', 'coordinator-v1');
    return new Response(response.body, { status: response.status, statusText: response.statusText, headers });
  }
}

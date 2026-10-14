import { afterEach, describe, expect, it, vi } from 'vitest';
import handler from './index';
import type { Env } from './config';

function fixture() {
  let order: Record<string, unknown> | null = null;
  const statements: Array<{sql: string; values: unknown[]}> = [];
  const db = { prepare(sql: string) {
    let values: unknown[] = [];
    const statement = {
      bind(...args: unknown[]) { values = args; return statement; },
      async first() { return sql.includes('ljr_orders WHERE id=?') ? order : null; },
      async run() {
        statements.push({sql, values});
        if (sql.includes('INSERT INTO ljr_orders')) order = { id: values[0], email: values[2] };
        return {success:true};
      }
    };
    return statement;
  }} as unknown as D1Database;
  const env = { DB:db, ENVIRONMENT:'test', PORTAL_ORIGIN:'https://ljr.tomaspisar.cz', STRIPE_SECRET_KEY:'sk_test_fixture',
    STRIPE_PRICE_LIFETIME:'price_lifetime', STRIPE_PRICE_SUBSCRIPTION:'price_monthly' } as Env;
  return {env, statements};
}
const request = (body: Record<string, unknown>) => new Request('https://api.tomaspisar.cz/api/longjumpreplay/checkout', {
  method:'POST', headers:{Origin:'https://tomaspisar.cz','Content-Type':'application/json','X-Idempotency-Key':'ljr_test_email_free_1234'}, body:JSON.stringify(body)
});
const consent = {accepted_purchase_terms:true, immediate_delivery_requested:true, withdrawal_rights_acknowledged:true};
afterEach(() => vi.unstubAllGlobals());

describe('email-free public licence checkout', () => {
  it.each(['price_lifetime','price_monthly'])('opens %s without an email and records consent evidence', async priceId => {
    const {env, statements} = fixture();
    let checkout = new URLSearchParams();
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      if (String(url).includes('/prices/')) return Response.json({id:priceId,unit_amount:499000,currency:'czk',product:{id:'prod_ljr',name:'LongJumpReplay'}});
      checkout = new URLSearchParams(String(init?.body));
      return Response.json({id:'cs_test',url:'https://checkout.stripe.com/c/pay/test'});
    }));
    const response = await handler.fetch(request({price_id:priceId,...consent}), env);
    expect(response.status).toBe(200);
    expect(checkout.has('customer_email')).toBe(false);
    expect(checkout.get('cancel_url')).toBe('https://tomaspisar.cz/products/long-jump-replay/#buy');
    expect(checkout.get('line_items[0][price]')).toBe(priceId);
    const insert = statements.find(item => item.sql.includes('INSERT INTO ljr_orders'))!;
    expect(insert.values[2]).toBe('');
    expect(insert.values.slice(16,19).every(value => typeof value === 'number' && value > 0)).toBe(true);
  });
  it('still rejects missing agreements and unlisted prices', async () => {
    const {env, statements} = fixture();
    expect((await handler.fetch(request({price_id:'price_lifetime'}),env)).status).toBe(422);
    expect((await handler.fetch(request({price_id:'price_unlisted',...consent}),env)).status).toBe(422);
    expect(statements.some(item => item.sql.includes('INSERT INTO ljr_orders'))).toBe(false);
  });
  it('redirects the old checkout before any account lookup', async () => {
    const {env, statements} = fixture();
    const response = await handler.fetch(new Request('https://ljr.tomaspisar.cz/checkout/?price=price_lifetime'),env);
    expect(response.headers.get('Location')).toBe('https://tomaspisar.cz/products/long-jump-replay/#buy');
    expect(statements).toHaveLength(0);
  });
});

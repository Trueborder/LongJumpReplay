/** Unpublished test fixtures only. Refuses live Stripe credentials. */
const key = process.env.ECONOMYSUITE_STRIPE_TEST_KEY;
if (!/^(sk|rk|rkcs)_test_/.test(key || '')) throw new Error('Set ECONOMYSUITE_STRIPE_TEST_KEY from an isolated Stripe sandbox. Live keys are refused.');
const drafts = [{ currency: 'coins', amounts: [1000, 5000, 10000] }, { currency: 'tokens', amounts: [10, 50, 100] }];
async function post(path, fields, idempotency) {
  const response = await fetch(`https://api.stripe.com/v1/${path}`, { method: 'POST', headers: { Authorization: `Bearer ${key}`, 'Content-Type': 'application/x-www-form-urlencoded', 'Stripe-Version': '2026-09-30.endive', 'Idempotency-Key': idempotency }, body: new URLSearchParams(fields), signal: AbortSignal.timeout(10000) });
  if (!response.ok) throw new Error(`Stripe ${path} failed (${response.status}).`);
  return response.json();
}
for (const group of drafts) for (const [index, amount] of group.amounts.entries()) {
  const fixture = `economysuite-draft-${group.currency}-${amount}-v1`;
  const product = await post('products', { name: `Pantheon — ${amount} ${group.currency} (sandbox draft)`, description: 'Unpublished sandbox fixture. The test price is not a proposed live price.', 'metadata[es_product]': 'economysuite', 'metadata[es_server]': 'pantheon', 'metadata[es_published]': 'false', 'metadata[es_sort]': String(index), 'metadata[es_fixture]': fixture }, `${fixture}-product`);
  const price = await post('prices', { product: product.id, currency: 'czk', unit_amount: '10000', 'metadata[es_currency]': group.currency, 'metadata[es_amount]': String(amount) }, `${fixture}-price`);
  await post(`products/${product.id}`, { default_price: price.id }, `${fixture}-default`);
  console.log(JSON.stringify({ product: product.id, price: price.id, currency: group.currency, amount, published: false }));
}

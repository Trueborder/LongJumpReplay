/** Unpublished sandbox rank products only. Never accepts live credentials or enables sales. */
const key=process.env.ECONOMYSUITE_STRIPE_TEST_KEY;
if(!/^(sk|rk|rkcs)_test_/.test(key||''))throw new Error('An isolated Stripe sandbox key is required. Live keys are refused.');
async function post(path,fields,idempotency){
  const response=await fetch('https://api.stripe.com/v1/'+path,{method:'POST',headers:{Authorization:'Bearer '+key,'Content-Type':'application/x-www-form-urlencoded','Stripe-Version':'2026-09-30.endive','Idempotency-Key':idempotency},body:new URLSearchParams(fields),signal:AbortSignal.timeout(10000)});
  if(!response.ok)throw new Error('Rank sandbox setup failed: HTTP '+response.status);return response.json();
}
for(const [rank,name,minor]of [['vip','VIP',3900],['vipplus','VIP+',6900],['mvp','MVP',9900]]){
  const seed='economysuite-rank-'+rank+'-7days-v1';
  const product=await post('products',{name:'Pantheon — '+name+' / 7 dní',description:'Seven calendar days from payment confirmation, including offline time. Higher ranks pause remaining lower-tier time. Shared boosters benefit all players. No recurring billing.','metadata[es_product]':'economysuite','metadata[es_server]':'pantheon','metadata[es_kind]':'rank','metadata[es_rank]':rank,'metadata[es_published]':'false'},seed+'-product');
  const price=await post('prices',{product:product.id,currency:'czk',unit_amount:String(minor),'metadata[es_duration_seconds]':'604800'},seed+'-price');
  await post('products/'+product.id,{default_price:price.id},seed+'-default');
  console.log(JSON.stringify({rank,product:product.id,price:price.id,published:false}));
}

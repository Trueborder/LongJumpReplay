const UPSTREAM='https://api.tomaspisar.cz/api/economysuite/public/summary';
const security={'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'",'X-Content-Type-Options':'nosniff','Referrer-Policy':'strict-origin-when-cross-origin','Permissions-Policy':'camera=(), microphone=(), geolocation=()'};
export async function handle(request,env,ctx,fetcher=fetch,cache=globalThis.caches?.default){
 const url=new URL(request.url);if(!['GET','HEAD'].includes(request.method))return new Response('Method not allowed',{status:405,headers:{...security,Allow:'GET, HEAD'}});
 if(url.pathname==='/api/status'){
  const key=new Request(url.origin+'/api/status'),hit=await cache?.match(key);if(hit)return hit;
  try{const upstream=await fetcher(UPSTREAM,{headers:{Accept:'application/json'},redirect:'error',signal:AbortSignal.timeout(6000)});if(!upstream.ok)throw Error('unavailable');const data=await upstream.json();
   if(data?.version!==1)throw Error('invalid version');
   const response=Response.json(data,{headers:{...security,'Cache-Control':'public, max-age=0, s-maxage=10'}});
   if(cache)ctx.waitUntil(cache.put(key,new Response(response.clone().body,{headers:{...security,'Content-Type':'application/json','Cache-Control':'public, max-age=10'}})));return response;
  }catch{return Response.json({version:1,fresh:false,updated_at:null,server:null,tournament:null,community:null},{headers:{...security,'Cache-Control':'no-store'}});}
 }
 if(url.pathname.startsWith('/api/'))return new Response('Not found',{status:404,headers:security});
 if(url.pathname==='/en')return Response.redirect(url.origin+'/en/'+url.search,308);
 const asset=await env.ASSETS.fetch(request),headers=new Headers(asset.headers);for(const [key,value]of Object.entries(security))headers.set(key,value);
 if(url.hostname!=='pantheon.tomaspisar.cz')headers.set('X-Robots-Tag','noindex');
 return new Response(request.method==='HEAD'?null:asset.body,{status:asset.status,headers});
}
export default{fetch:handle};

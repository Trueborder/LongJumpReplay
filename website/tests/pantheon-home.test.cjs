const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const base=path.join(__dirname,'../pantheon');
const load=()=>import('../pantheon/render.mjs');
test('Pantheon has independently localized static pages with canonical SEO and useful navigation',async()=>{
 const {render}=await load();for(const lang of ['cs','en']){const html=render(lang);assert.match(html,new RegExp(`<html lang="${lang}"`));assert.equal((html.match(/<h1\b/g)||[]).length,1);for(const word of ['hreflang="cs"','hreflang="en"','og:image','twitter:card','id="events"','id="start"','/web link','https://dc.gg/pantheon','map.pantheon.tomaspisar.cz','/economysuite/rank'])assert.ok(html.includes(word),word);assert.doesNotMatch(html,/undefined|TODO|lorem ipsum|youtube|iframe|autoplay/i);assert.match(html,/illustration|ilustrace/);}
 assert.match(render('en'),/How to join/);assert.match(render('cs'),/Jak se připojit/);
});
test('public event renderer safely handles stale, absent, completed, zero and malicious data',async()=>{
 const {eventMarkup}=await import('../pantheon/assets/site.mjs'),{content}=await import('../pantheon/assets/content.mjs');
 const t=content.cs,data={version:1,fresh:true,updated_at:100,server:{players:0},tournament:null,community:null};
 assert.match(eventMarkup(data,t,100),/Právě neprobíhá žádný turnaj/);assert.doesNotMatch(eventMarkup({...data,updated_at:69},t,100),/Registrace a pavouk/);
 const attack={...data,tournament:{state:'REGISTRATION',players:0,size:4,best_of:3,policy:'SAME',mode:'<img src=x onerror=x>',summary:'<script>evil()</script>'},community:{title:'<img>',active:true,progress:0,target:100,ends_at:200}};
 const html=eventMarkup(attack,t,100);assert.match(html,/0\/4 · BO3/);assert.match(html,/value="0"/);assert.doesNotMatch(html,/<img|<script/);assert.match(html,/&lt;script&gt;/);
 assert.doesNotMatch(eventMarkup({...attack,community:{...attack.community,progress:100}},t,100),/<progress/);
 assert.doesNotMatch(eventMarkup({...attack,community:{...attack.community,ends_at:99}},t,100),/<progress/);
});
test('homepage motion is scoped and responsive with stable live data and clipboard fallback',()=>{
 const css=fs.readFileSync(path.join(base,'assets/site.css'),'utf8'),js=fs.readFileSync(path.join(base,'assets/site.mjs'),'utf8');
 for(const value of ['prefers-reduced-motion','hover:hover','pointer:fine','position:sticky','max-width:640px','.keyboard'])assert.ok(css.includes(value),value);
 assert.doesNotMatch(css,/transition:\s*all/);assert.match(js,/document\.hidden/);assert.match(js,/15000/);assert.match(js,/credentials:'omit'/);assert.match(js,/navigator\.clipboard\.writeText/);assert.match(js,/input\.select\(\)/);assert.match(js,/url\.hash=location\.hash/);
 for(const file of ['pantheon-hero.webp','pantheon-mobile.webp','pantheon-og.jpg'])assert.ok(fs.statSync(path.join(base,'assets',file)).size<512*1024);
});
test('homepage proxy pins the read-only endpoint, forwards no cookies and fails closed',async()=>{
 const {handle}=await import('../pantheon/worker.mjs');let called;
 const env={ASSETS:{fetch:async()=>new Response('page')}};const ctx={waitUntil:()=>{}};
 const fetcher=async(url,options)=>{called={url,options};return Response.json({version:1,fresh:false,server:null});};
 const response=await handle(new Request('https://pantheon.tomaspisar.cz/api/status?target=https://evil.test',{headers:{Cookie:'private-session'}}),env,ctx,fetcher,null);
 assert.equal(response.status,200);assert.equal(called.url,'https://account.pantheon.tomaspisar.cz/api/economysuite/public/summary');assert.equal(called.options.headers.Cookie,undefined);assert.match(response.headers.get('Content-Security-Policy'),/frame-ancestors 'none'/);
 const failed=await handle(new Request('https://pantheon.tomaspisar.cz/api/status'),env,ctx,async()=>{throw Error('down');},null);assert.equal((await failed.json()).fresh,false);assert.equal(failed.headers.get('cache-control'),'no-store');
 assert.equal((await handle(new Request('https://pantheon.tomaspisar.cz/api/status',{method:'POST'}),env,ctx,fetcher,null)).status,405);
 assert.equal((await handle(new Request('https://pantheon.tomaspisar.cz/api/admin'),env,ctx,fetcher,null)).status,404);
 assert.equal((await handle(new Request('https://preview.workers.dev/'),env,ctx,fetcher,null)).headers.get('X-Robots-Tag'),'noindex');
});
test('production proxy uses its service binding for only the fixed anonymous summary',async()=>{
 const {handle}=await import('../pantheon/worker.mjs');let called;
 const env={PUBLIC_API:{fetch:async(url,options)=>{called={url,options};return Response.json({version:1,fresh:true,server:{players:0}});}}};
 const response=await handle(new Request('https://pantheon.tomaspisar.cz/api/status',{headers:{Cookie:'private'}}),env,{waitUntil(){}},()=>{throw Error('must not use public fetch');},null);
 assert.equal((await response.json()).fresh,true);assert.equal(called.url,'https://account.pantheon.tomaspisar.cz/api/economysuite/public/summary');assert.equal(called.options.headers.Cookie,undefined);assert.equal(called.options.redirect,'manual');
 const redirect=await handle(new Request('https://pantheon.tomaspisar.cz/api/status'),{}, {waitUntil(){}},async()=>new Response(null,{status:302,headers:{Location:'https://evil.test'}}),null);assert.equal((await redirect.json()).fresh,false);
 const config=JSON.parse(fs.readFileSync(path.join(base,'wrangler.jsonc'),'utf8'));
 assert.deepEqual(config.services,[{binding:'PUBLIC_API',service:'longjumpreplay-licensing-production'}]);
});
test('edge cache remains ten seconds without making the browser reuse stale status',async()=>{
 const {handle}=await import('../pantheon/worker.mjs');
 const cached=Response.json({version:1,fresh:true},{headers:{'Cache-Control':'public, max-age=10'}});
 const result=await handle(new Request('https://pantheon.tomaspisar.cz/api/status'),{}, {},()=>{throw Error('cache miss');},{match:async()=>cached});
 assert.equal(result.headers.get('Cache-Control'),'no-store');
 assert.match(fs.readFileSync(path.join(base,'assets/site.mjs'),'utf8'),/cache:'no-store'/);
});

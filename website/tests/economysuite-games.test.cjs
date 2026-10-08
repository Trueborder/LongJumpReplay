const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const script = fs.readFileSync(path.join(__dirname,'../tomaspisar.cz/account/economysuite/games.js'),'utf8');
function harness() {
  const events={},storage=new Map(),elements={};
  for(const id of ['game-form','game-type','game-currency','game-choice','game-stake','game-filter','game-bet','game-recover','game-more']) elements[id]={id,disabled:false,addEventListener:(name,fn)=>{events[id+':'+name]=fn;},focus(){},style:{}};
  const sandbox={window:{},document:{getElementById:id=>elements[id],activeElement:null},sessionStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},crypto:require('node:crypto').webcrypto,requestAnimationFrame:fn=>fn(),Date};
  vm.runInNewContext(script,sandbox);
  const account={email:'test@example.com',link:{uuid:'test'},snapshot:{coins:1000,tokens:100,debt:{coins:0,tokens:0}}};
  const config={enabled:true,server_enabled:true,connected:true,supported:true,rules_version:'es-games-1',tables:{coin:[{probability:50,factor:19},{probability:50,factor:0}],wheel:[{probability:5,factor:0},{probability:20,factor:5},{probability:20,factor:8},{probability:25,factor:10},{probability:20,factor:12},{probability:10,factor:20}]}};
  let rounds=[],html='',submitted=[];
  const c={account,t:(cs,en)=>en,escape:String,number:n=>String(n||0),date:String,panel:(title,body)=>`<section>${title}${body}</section>`,currencyIcon:c=>c,table:(heads,rows)=>heads.join('|')+rows.join('|'),row:cells=>cells.join('|'),empty:()=>'',status(){},api:async(url,data)=>{if(data){submitted.push(data);throw new Error('Lost response');}return url.endsWith('/config')?config:{rounds};},render:()=>{html=sandbox.window.ESGames.render(c);}};
  return {games:sandbox.window.ESGames,c,events,elements,storage,config,submitted,get html(){return html;},setRounds:value=>rounds=value};
}
test('games renders total payouts and safely handles malformed numeric input',async()=>{
  const h=harness();await h.games.load(h.c.api,h.c.account);h.c.render();h.games.bind(h.c);
  assert.match(h.html,/Bet 100 coins/);assert.match(h.html,/1.9×.*190 coins/);
  h.events['game-stake:input']({target:{value:'1e999',selectionStart:null}});
  assert.match(h.html,/id="game-bet"[^>]*disabled/);
  h.events['game-currency:change']({target:{value:'tokens'}});
  h.events['game-stake:input']({target:{value:'10',selectionStart:null}});
  assert.match(h.html,/Bet 10 tokens/);
});
test('pending rounds disable betting and never reveal a speculative result',async()=>{
  const h=harness();h.setRounds([{id:'round',game:'coin',currency:'coins',stake:100,state:'pending',created_at:Date.now()/1000,payout:null,net:null,result:null}]);
  await h.games.load(h.c.api,h.c.account);h.c.render();
  assert.match(h.html,/id="game-bet"[^>]*disabled/);assert.match(h.html,/Waiting for server/);assert.doesNotMatch(h.html,/Evaluated:/);
});
test('double submit and uncertain recovery use exactly the original key',async()=>{
  const h=harness();await h.games.load(h.c.api,h.c.account);h.c.render();h.games.bind(h.c);
  const submit=h.events['game-form:submit'];submit({preventDefault(){}});submit({preventDefault(){}});
  await new Promise(resolve=>setImmediate(resolve));assert.equal(h.submitted.length,1);assert.equal(h.storage.size,1);
  assert.match(h.html,/Recover original bet/);h.games.bind(h.c);h.events['game-recover:click']();
  await new Promise(resolve=>setImmediate(resolve));assert.equal(h.submitted.length,2);assert.equal(h.submitted[0].idempotency_key,h.submitted[1].idempotency_key);
});
test('disabled or unsupported servers never enable the submit control',async()=>{
  const h=harness();h.config.enabled=false;await h.games.load(h.c.api,h.c.account);h.c.render();assert.match(h.html,/id="game-bet"[^>]*disabled/);
  h.config.enabled=true;h.config.supported=false;h.c.render();assert.match(h.html,/id="game-bet"[^>]*disabled/);
  h.config.supported=true;h.config.server_enabled=false;h.c.render();assert.match(h.html,/id="game-bet"[^>]*disabled/);assert.match(h.html,/Games are disabled on the server/);
  delete h.config.server_enabled;h.c.render();assert.match(h.html,/id="game-bet"[^>]*disabled/);
});

test('each game animates a neutral wait and reveals only the acknowledged result',async()=>{
  for (const game of ['coin','dice','wheel']) {
    const h=harness();
    const round={id:'animated-'+game,game,currency:'coins',stake:100,state:'pending',created_at:Date.now()/1000,payout:null,net:null,result:null};
    h.setRounds([round]);await h.games.load(h.c.api,h.c.account);h.c.render();h.games.bind(h.c);
    assert.match(h.html,new RegExp(`data-game="${game}" data-phase="waiting"`));
    assert.doesNotMatch(h.html,/is-revealing/);
    if(game!=='wheel')assert.match(h.html,/id="game-piece">\?<\/div>/);
    round.state='complete';round.payout=190;round.net=90;
    round.result=JSON.stringify({state:'complete',outcome:game==='coin'?'heads':game==='wheel'?'4':'win',roll:7});
    h.events['game-type:change']({target:{value:game}});
    assert.match(h.html,/is-revealing/);assert.match(h.html,/data-phase="complete"/);
    if(game==='coin')assert.match(h.html,/id="game-piece">Heads/);
    if(game==='dice')assert.match(h.html,/id="game-piece">07/);
    h.games.bind(h.c);h.c.render();assert.doesNotMatch(h.html,/is-revealing/);
  }
  const css=fs.readFileSync(path.join(__dirname,'../tomaspisar.cz/account/economysuite/app.css'),'utf8');
  assert.match(css,/@media\(prefers-reduced-motion:reduce\).*es-game-wait-fade/);
});

// Local, synthetic UI fixture. This does not test the authoritative plugin bridge.
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '../tomaspisar.cz');
const tables = { coin:[{probability:50,factor:19},{probability:50,factor:0}],dice10:[{probability:10,factor:95},{probability:90,factor:0}],dice25:[{probability:25,factor:38},{probability:75,factor:0}],dice50:[{probability:50,factor:19},{probability:50,factor:0}],wheel:[{probability:5,factor:0},{probability:20,factor:5},{probability:20,factor:8},{probability:25,factor:10},{probability:20,factor:12},{probability:10,factor:20}] };
let rounds = [];
const snapshot = { coins: 10000, tokens: 100, pending_tokens: 25, debt: {coins:0,tokens:0} };
const server = http.createServer(async (req,res) => {
  const url = new URL(req.url, 'http://localhost');
  const json = value => {res.writeHead(200,{'Content-Type':'application/json','Cache-Control':'no-store'});res.end(JSON.stringify(value));};
  if(url.pathname.startsWith('/api/')) {
    if(url.pathname.endsWith('/account'))return json({email:'fixture@example.com',link:{uuid:'11111111-1111-4111-8111-111111111111',name:'TestPlayer'},snapshot,synced_at:Math.floor(Date.now()/1000),server_status:'connected',server_online:true});
    if(url.pathname.endsWith('/config'))return json({enabled:true,server_enabled:true,connected:true,supported:true,rules_version:'es-games-1',tables});
    if(url.pathname.endsWith('/rounds') && req.method==='POST') {
      let raw='';for await(const chunk of req)raw+=chunk;
      const bet=JSON.parse(raw),old=rounds.find(r=>r.idempotency_key===bet.idempotency_key);if(old)return json({round:old});
      const round={...bet,id:crypto.randomUUID(),cursor:rounds.length+1,state:'pending',created_at:Math.floor(Date.now()/1000),payout:null,net:null,result:null};rounds.unshift(round);json({round});
      setTimeout(()=>{round.state='complete';const factor=bet.game==='wheel'?12:bet.game==='dice'?tables['dice'+bet.choice][0].factor:19;round.payout=bet.stake/10*factor;round.net=round.payout-bet.stake;snapshot[bet.currency]+=round.net;round.result=JSON.stringify({state:'complete',outcome:bet.game==='wheel'?'4':bet.game==='coin'?bet.choice:'win',roll:bet.game==='wheel'?70:bet.game==='coin'?(bet.choice==='heads'?0:50):7,payout:round.payout,net:round.net,balance:snapshot[bet.currency],rules_version:'es-games-1'});},2500);return;
    }
    if(url.pathname.endsWith('/rounds'))return json({rounds});
    const round=rounds.find(r=>url.pathname.endsWith('/'+r.id));if(round)return json({round});
    return json({});
  }
  let pathname=url.pathname;
  if(pathname.startsWith('/economysuite/'))pathname=/\.(js|css)$/.test(pathname)?'/account'+pathname:'/account/economysuite/index.html';
  const filename=path.resolve(root,'.'+pathname);
  if(!filename.startsWith(root+path.sep)){res.writeHead(403);return res.end();}
  try {let bytes=fs.readFileSync(filename);if(filename.endsWith('.html'))bytes=Buffer.from(bytes.toString().replaceAll('https://tomaspisar.cz',''));
    res.writeHead(200,{'Content-Type':filename.endsWith('.css')?'text/css':filename.endsWith('.js')?'application/javascript':filename.endsWith('.svg')?'image/svg+xml':filename.endsWith('.png')?'image/png':filename.endsWith('.woff2')?'font/woff2':'text/html'});res.end(bytes);
  } catch {res.writeHead(404);res.end('Not found');}
});
server.listen(8794,'127.0.0.1',()=>console.log('Synthetic games UI fixture: http://127.0.0.1:8794/economysuite/games'));

/** Local-only Paper + real Worker rehearsal. Never contacts production or Stripe. */
import { readFileSync, writeFileSync, mkdirSync, existsSync, readdirSync } from 'node:fs';
import { resolve, join } from 'node:path';
import { randomUUID, randomBytes, createHash } from 'node:crypto';
import { createServer } from 'node:https';
import { spawn, execFileSync } from 'node:child_process';
import { build } from 'esbuild';
import { Miniflare, convertV4MiniflareOptions } from 'miniflare';
import assert from 'node:assert/strict';

const pluginRoot=resolve(process.env.ECONOMYSUITE_TEST_PLUGIN_ROOT || '../../PROJECTS/EconomySuite');
const serverRoot=join(pluginRoot,'outputs/games-paper');
const java=join(pluginRoot,'tools/jdk21/jdk-21.0.12.1+1/bin/java.exe');
const keytool=join(pluginRoot,'tools/jdk21/jdk-21.0.12.1+1/bin/keytool.exe');
if(!/^eula\s*=\s*true\s*$/im.test(existsSync(join(serverRoot,'eula.txt'))?readFileSync(join(serverRoot,'eula.txt'),'utf8'):'')) {
  throw new Error('Accept the Minecraft EULA yourself in the isolated server eula.txt before running this rehearsal.');
}
for(const file of ['paper.jar','plugins/Vault.jar'])assert.ok(existsSync(join(serverRoot,file)),`Missing ${file}; see GAMES_TESTING.md`);
const pluginJar=readdirSync(join(pluginRoot,'build/libs')).filter(f=>/^EconomySuite-.*\.jar$/.test(f)).sort((a,b)=>a.localeCompare(b,undefined,{numeric:true})).at(-1);assert.ok(pluginJar);
writeFileSync(join(serverRoot,'plugins',pluginJar),readFileSync(join(pluginRoot,'build/libs',pluginJar)));
const secret=randomBytes(32).toString('hex'), origin='https://localhost:9443';
const certPassword=randomBytes(20).toString('hex');
// A new file each run avoids overwriting or globally trusting an existing certificate.
const certFile=join(serverRoot,`test-${randomUUID()}.p12`);
execFileSync(keytool,['-genkeypair','-alias','games-local','-keyalg','RSA','-keysize','2048','-validity','2','-dname','CN=localhost','-ext','SAN=dns:localhost,ip:127.0.0.1','-storetype','PKCS12','-keystore',certFile,'-storepass',certPassword,'-keypass',certPassword,'-noprompt'],{stdio:'ignore',windowsHide:true});
mkdirSync(join(serverRoot,'plugins/EconomySuite'),{recursive:true});
writeFileSync(join(serverRoot,'plugins/EconomySuite/config.yml'),`language: en\nwebsite:\n  enabled: true\n  environment: test\n  games-test-enabled: true\n  portal-origin: '${origin}'\n  bridge-secret: '${secret}'\n`);
writeFileSync(join(serverRoot,'server.properties'),'server-ip=127.0.0.1\nserver-port=25591\nonline-mode=true\nlevel-type=minecraft:flat\ngenerate-structures=false\nview-distance=2\nsimulation-distance=2\nmax-players=1\nspawn-protection=0\nenable-rcon=false\n');
const bundled=await build({entryPoints:['src/index.ts'],bundle:true,format:'esm',platform:'browser',write:false});
const mf=new Miniflare(convertV4MiniflareOptions({modules:true,script:bundled.outputFiles[0].text,compatibilityDate:'2026-08-01',d1Databases:['DB','ECONOMYSUITE_DB'],bindings:{ENVIRONMENT:'test',PORTAL_ORIGIN:origin,ECONOMYSUITE_PORTAL_ORIGIN:origin,ECONOMYSUITE_GAMES_ENABLED:'true',ECONOMYSUITE_PURCHASES_ENABLED:'false',ECONOMYSUITE_BRIDGE_SECRET:secret,VERIFICATION_PEPPER:randomBytes(32).toString('hex')}}));
for(const [binding,directory] of [['DB','migrations'],['ECONOMYSUITE_DB','economysuite-migrations']]) {
  const db=await mf.getD1Database(binding);
  for(const migration of readdirSync(directory).filter(f=>f.endsWith('.sql')).sort()) {
    const sql=readFileSync(join(directory,migration),'utf8').replace(/--[^\n]*/g,'').split(/;(?!\s*END\b)/i).map(s=>s.replace(/\r?\n/g,' ').trim()).filter(Boolean).join(';\n')+';';await db.exec(sql);
  }
}
const db=await mf.getD1Database('DB'),es=await mf.getD1Database('ECONOMYSUITE_DB');
const https=createServer({pfx:readFileSync(certFile),passphrase:certPassword},async(req,res)=>{
  try {let raw='';for await(const chunk of req)raw+=chunk;
    const response=await mf.dispatchFetch(origin+req.url,{method:req.method,headers:req.headers,body:raw||undefined});
    res.writeHead(response.status,Object.fromEntries(response.headers));res.end(Buffer.from(await response.arrayBuffer()));
  }catch{res.writeHead(500);res.end('Local fixture failed');}
});
await new Promise(r=>https.listen(9443,'127.0.0.1',r));
let paper;
const delay=ms=>new Promise(r=>setTimeout(r,ms));
const hash=value=>createHash('sha256').update(value).digest('base64url');
const fixtures=[];
async function fixture(game,currency,choice,scenario='normal') {
  const uuid=randomUUID(),customer='games-test-'+randomUUID(),token=randomBytes(32).toString('hex'),csrf=randomBytes(32).toString('hex'),now=Math.floor(Date.now()/1000);
  await es.batch([
    db.prepare('INSERT INTO customers(id,email,created_at,updated_at) VALUES(?,?,?,?)').bind(customer,customer+'@example.com',now,now),
    db.prepare('INSERT INTO customer_password_credentials(customer_id,password_hash,created_at,updated_at,password_changed_at) VALUES(?,?,?,?,?)').bind(customer,'unused-test-only',now,now,now),
    db.prepare('INSERT INTO portal_sessions(id,customer_id,token_hash,created_at,expires_at,last_seen_at,csrf_token_hash) VALUES(?,?,?,?,?,?,?)').bind(randomUUID(),customer,hash(token),now,now+3600,now,hash(csrf)),
  ]);
  await es.prepare('INSERT INTO player_links(customer_id,uuid,name,linked_at) VALUES(?,?,?,?)').bind(customer,uuid,'GamesTest',now).run();
  const entry={uuid,customer,token,csrf,game,currency,choice,scenario};fixtures.push(entry);return entry;
}
async function portal(f,path,data) {
  const response=await mf.dispatchFetch(origin+'/api/economysuite/'+path,{method:data?'POST':'GET',headers:{Cookie:`__Host-es-session=${f.token}`,Origin:origin,'X-CSRF-Token':f.csrf,'Content-Type':'application/json'},body:data?JSON.stringify(data):undefined});
  const result=await response.json();assert.ok(response.ok,`${path}: ${response.status} ${result.error || ''}`);return result;
}
// Python writes only the synthetic UUIDs in this named local test database.
function seedWallets() {
  const sql=`import sqlite3,json,sys\nc=sqlite3.connect(sys.argv[1],timeout=15)\nfor f in json.loads(sys.argv[2]):\n c.execute('INSERT OR REPLACE INTO accounts(uuid,balance) VALUES(?,?)',(f['uuid'],10000))\n c.execute('INSERT OR REPLACE INTO token_wallets_v2(uuid,balance,pending) VALUES(?,?,?)',(f['uuid'],0 if f['scenario']=='pending' else 10000,100 if f['scenario']=='pending' else 0))\n if f['scenario']=='debt':c.execute('INSERT OR REPLACE INTO web_debts(uuid,coins,tokens) VALUES(?,1,0)',(f['uuid'],))\nc.commit()\n`;
  execFileSync('py.exe',['-3','-c',sql,join(serverRoot,'plugins/EconomySuite/economy.db'),JSON.stringify(fixtures)],{windowsHide:true});
}
try {
  const log=join(serverRoot,'games-rehearsal.log');writeFileSync(log,'');
  paper=spawn(java,['-Xms512M','-Xmx1G','-Djava.net.preferIPv4Stack=true',`-Djavax.net.ssl.trustStore=${certFile}`,`-Djavax.net.ssl.trustStorePassword=${certPassword}`,'-jar','paper.jar','--nogui'],{cwd:serverRoot,windowsHide:true,stdio:['pipe','pipe','pipe']});
  paper.stdout.on('data',chunk=>{writeFileSync(log,chunk,{flag:'a'});});paper.stderr.on('data',chunk=>{writeFileSync(log,chunk,{flag:'a'});});
  let ready=false;
  for(let i=0;i<90;i++){if(paper.exitCode!==null)throw new Error(`Paper exited (${paper.exitCode}); inspect ${log}`);const status=await es.prepare("SELECT games_version,games_enabled FROM bridge_status WHERE server='pantheon'").first();if(status?.games_version==='es-games-1' && status.games_enabled===1){ready=true;break;}await delay(1000);}
  assert.ok(ready,`Paper bridge did not connect; inspect ${log}`);
  for(const currency of ['coins','tokens'])for(const [game,choice] of [['coin','heads'],['coin','tails'],['dice','10'],['dice','25'],['dice','50'],['wheel','']])await fixture(game,currency,choice);
  await fixture('wheel','tokens','','pending');await fixture('wheel','tokens','','debt');seedWallets();
  for(const f of fixtures){f.bet={game:f.game,currency:f.currency,choice:f.choice,stake:f.currency==='coins'?100:10,rules_version:'es-games-1',idempotency_key:randomUUID()};f.round=(await portal(f,'games/rounds',f.bet)).round;}
  for(const f of fixtures){let result;for(let i=0;i<45;i++){result=(await portal(f,'games/rounds/'+f.round.id)).round;if(result.state!=='pending')break;await delay(1000);}assert.notEqual(result.state,'pending');
    const detail=JSON.parse(result.result);if(f.scenario==='normal'){assert.equal(result.state,'complete');assert.equal(detail.net,result.payout-f.bet.stake);}else{assert.equal(result.state,'rejected');assert.equal(detail.error,f.scenario==='pending'?'insufficient_funds':'debt');}
    assert.deepEqual((await portal(f,'games/rounds',f.bet)).round,result);
    console.log(`PASS ${f.game}/${f.choice || 'six sectors'} ${f.currency} ${f.scenario}: ${result.state}`);
  }
  const pending=await es.prepare("SELECT COUNT(*) n FROM game_rounds WHERE state='pending'").first('n');assert.equal(pending,0);
  console.log('PASS real Paper signed poll/settlement/ack, offline synthetic players, both currencies, pending tokens, debt, API replay');
} finally {
  if(paper && paper.exitCode===null){paper.stdin.write('stop\n');await Promise.race([new Promise(r=>paper.once('exit',r)),delay(20000)]);if(paper.exitCode===null)paper.kill();}
  await new Promise(r=>https.close(r));await mf.dispose();
}

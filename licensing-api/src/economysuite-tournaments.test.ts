/// <reference types="node" />
import {afterEach,beforeEach,describe,it,expect} from 'vitest';
import {Miniflare,convertV4MiniflareOptions} from 'miniflare';
import {readFileSync,readdirSync} from 'node:fs';
import {tournamentSnapshot,skinUrl,tournamentAdmin,tournamentBridge,tournamentRoute} from './economysuite-tournaments';
import {economySuite,type PlayerAuth} from './economysuite';
import type {Env} from './config';
import {sha256} from './crypto';

const uuid='11111111-1111-4111-8111-111111111111',instance='22222222-2222-4222-8222-222222222222';
const head='https://textures.minecraft.net/texture/'+'a'.repeat(64);
const snapshot=()=>({version:1,id:'test-tournament',instance,revision:7,state:'REGISTRATION',size:4,best_of:3,players:[{uuid,name:'Player',skin:head}],online:[{uuid,name:'Player',eligible:true}],catalog:[{id:'safe-item',category:'items',name:'Sword',privateNBT:'hidden'}],times:{'inter-match-delay-seconds':30},matches:[]});
const player:PlayerAuth={customer:{id:'player-account',email:'player@example.com'},credential:{password_hash:'fixture'}};
const owner:PlayerAuth={customer:{id:'owner-account',email:'xpisar10@gmail.com'},credential:{password_hash:'fixture'}};
const req=(path:string,data?:unknown)=>new Request('https://account.pantheon.tomaspisar.cz/api/economysuite/tournament'+path,{method:data?'POST':'GET',headers:{Cookie:'__Host-es-session=fixture-session'},...(data?{body:JSON.stringify(data)}:{})});
describe('tournament safe DTO',()=>{
  it('only allows Mojang skin textures, including normalized legacy HTTP URLs',()=>{
    expect(skinUrl(head)).toBe(head);expect(skinUrl(head.replace('https:','http:'))).toBe(head);
    for(const value of ['javascript:alert(1)','https://evil.example/a','https://textures.minecraft.net.evil.example/texture/'+'a'.repeat(64),head+'?private=true','file:///etc/passwd'])expect(skinUrl(value)).toBe('');
  });
  it('bounds collections and removes private data and raw item metadata',()=>{
    const safe=tournamentSnapshot({...snapshot(),online:Array(600).fill({uuid,name:'Player',ip:'secret'}),catalog:Array(1100).fill({id:'item',privateNBT:'secret'})});
    expect(safe.online).toHaveLength(500);expect(safe.catalog).toHaveLength(1000);expect(JSON.stringify(safe)).not.toContain('secret');expect(tournamentSnapshot(null).version).toBe(0);
  });
});
describe('tournament account authorization and outbox',()=>{
  let runtime:Miniflare,db:D1Database,env:Env;
  beforeEach(async()=>{
    runtime=new Miniflare(convertV4MiniflareOptions({modules:true,script:'export default {fetch(){return new Response("ok")}}',d1Databases:['DB','ES'],compatibilityDate:'2026-08-01'}));
    db=await runtime.getD1Database('ES');const shared=await runtime.getD1Database('DB');
    for(const [folder,target] of [['economysuite-migrations',db],['migrations',shared]] as const)for(const file of readdirSync(folder).filter(f=>f.endsWith('.sql')).sort())await target.exec(readFileSync(folder+'/'+file,'utf8').replace(/--[^\n]*/g,'').split(/;(?!\s*END\b)/i).map(s=>s.replace(/\r?\n/g,' ').trim()).filter(Boolean).join(';\n')+';');
    env={DB:shared,ECONOMYSUITE_DB:db} as Env;
    await db.prepare('INSERT INTO player_links(customer_id,uuid,name,linked_at) VALUES(?,?,?,?)').bind(player.customer.id,uuid,'Player',1).run();
    await tournamentBridge(db,'/sync',{snapshot:snapshot()});
  });
  afterEach(async()=>{await runtime.dispose();});
  const action=(name='join',payload={})=>({action:name,payload,tournament_id:'test-tournament',revision:7,instance,idempotency_key:crypto.randomUUID()});
  it('requires login and CSRF even for direct endpoint access',async()=>{
    expect((await economySuite(req('/action',action()),env,{authenticate:async()=>null,mutation:async()=>true})).status).toBe(401);
    expect((await economySuite(req('/action',action()),env,{authenticate:async()=>player,mutation:async()=>false})).status).toBe(403);
  });
  it('pins the owner to a stable account ID and never transfers ownership to a recreated email',async()=>{
    expect(await tournamentAdmin(db,player)).toBe(false);expect(await tournamentAdmin(db,owner)).toBe(true);
    expect(await tournamentAdmin(db,{...owner,customer:{...owner.customer,id:'recreated-account'}})).toBe(false);
  });
  it('public account reads omit catalog and roster and report only their own online eligibility',async()=>{
    const result=await (await tournamentRoute(req(''),env,db,player,uuid,{})).json() as {snapshot:Record<string,unknown>;player_online:boolean;admin:boolean};
    expect(result.admin).toBe(false);expect(result.player_online).toBe(true);expect(result.snapshot).not.toHaveProperty('catalog');expect(result.snapshot).not.toHaveProperty('online');expect(result.snapshot.players).toHaveLength(1);
  });
  it('rejects unauthorized, offline, stale and forged UUID requests; deduplicates retries',async()=>{
    expect((await tournamentRoute(req('/action',{}),env,db,player,uuid,action('cancel'))).status).toBe(403);
    expect((await tournamentRoute(req('/action',{}),env,db,player,null,action())).status).toBe(409);
    const body=action();expect((await tournamentRoute(req('/action',body),env,db,player,uuid,{...body,revision:6})).status).toBe(409);
    expect((await tournamentRoute(req('/action',body),env,db,player,uuid,{...body,player_uuid:'forged'})).status).toBe(202);
    expect((await tournamentRoute(req('/action',body),env,db,player,uuid,body)).status).toBe(200);
    const queued=await db.prepare('SELECT player_uuid FROM tournament_operations').first<{player_uuid:string}>();expect(queued?.player_uuid).toBe(uuid);expect(await db.prepare('SELECT COUNT(*) n FROM tournament_operations').first('n')).toBe(1);
    expect((await tournamentRoute(req('/action',body),env,db,player,uuid,{...body,payload:{different:true}})).status).toBe(409);
  });
  it('invalidates queued signups after unlink and never dispatches an expired request',async()=>{
    await tournamentRoute(req('/action',{}),env,db,player,uuid,action());await db.prepare('DELETE FROM player_links').run();
    expect((await (await tournamentBridge(db,'/sync',{snapshot:snapshot()})).json() as {operations:unknown[]}).operations).toHaveLength(0);
    await db.prepare('UPDATE tournament_operations SET expires_at=0').run();await tournamentBridge(db,'/sync',{snapshot:snapshot()});
    expect(await db.prepare('SELECT state FROM tournament_operations').first('state')).toBe('expired');
  });
  it('requires session-bound fresh reauthentication and explicit destructive confirmation',async()=>{
    const body=action('cancel');expect((await tournamentRoute(req('/action',body),env,db,owner,null,body)).status).toBe(403);
    const at=Math.floor(Date.now()/1000);await db.prepare('INSERT INTO tournament_reauth VALUES(?,?,?,?)').bind(await sha256('grant'),owner.customer.id,await sha256('__Host-es-session=fixture-session'),at+600).run();
    expect((await tournamentRoute(req('/action',body),env,db,owner,null,{...body,reauth_token:'grant'})).status).toBe(400);
    expect((await tournamentRoute(req('/action',body),env,db,owner,null,{...body,reauth_token:'grant',confirm:true})).status).toBe(202);
    const ack={id:body.idempotency_key,success:true,message:'Cancelled'};await tournamentBridge(db,'/ack',ack);await tournamentBridge(db,'/ack',{...ack,success:false});expect(await db.prepare('SELECT state FROM tournament_operations').first('state')).toBe('complete');
  });
  it('stores terminal history once without rewriting it on later synchronization',async()=>{
    expect(await db.prepare("SELECT COUNT(*) n FROM tournament_snapshots WHERE id!='current'").first('n')).toBe(0);
    await tournamentBridge(db,'/sync',{snapshot:{...snapshot(),state:'COMPLETED',summary:'Original prizes'}});
    await tournamentBridge(db,'/sync',{snapshot:{...snapshot(),state:'COMPLETED',summary:'Changed afterwards'}});
    const saved=await db.prepare("SELECT payload FROM tournament_snapshots WHERE id='test-tournament'").first<string>('payload');expect(JSON.parse(saved!).summary).toBe('Original prizes');
  });
});

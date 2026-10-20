import {describe,it,expect,beforeEach,afterEach} from 'vitest';
import {Miniflare,convertV4MiniflareOptions} from 'miniflare';
import {readFileSync} from 'node:fs';
import {publicSnapshot,publicSummary,savePublicSnapshot} from './economysuite-public';
import {economySuite} from './economysuite';
import type {Env} from './config';
describe('public snapshot privacy and validation',()=>{
 it('keeps only explicitly public fields, strips formatting and preserves zero counts',()=>{
  const input={version:1,enabled:true,email:'private',server:{players:0,capacity:50,version:'1.21.11',ip:'private'},tournament:{state:'REGISTRATION',players:2,size:4,best_of:3,mode:'Mace',summary:'&6Keys',online:[{name:'Private'}],catalog:['private']},community:{active:true,title:'&aHunt',progress:0,target:100,ends_at:1000,contributors:['private']}};
  const output=publicSnapshot(input);expect(output.server.players).toBe(0);expect(output.community?.title).toBe('Hunt');expect(output.tournament?.summary).toBe('Keys');expect(JSON.stringify(output)).not.toMatch(/private|contributors|catalog|online/);
 });
 it('rejects draft/completed tournaments, invalid numbers and unknown versions',()=>{
  expect(publicSnapshot({version:2,enabled:true}).enabled).toBe(false);
  expect(publicSnapshot({tournament:{state:'DRAFT'}}).tournament).toBeNull();expect(publicSnapshot({tournament:{state:'COMPLETED'}}).tournament).toBeNull();
  expect(publicSnapshot({server:{players:-1,capacity:Infinity}}).server).toMatchObject({players:0,capacity:0});
 });
});
describe('anonymous public summary with isolated D1 storage',()=>{
 let runtime:Miniflare,db:D1Database;
 beforeEach(async()=>{runtime=new Miniflare(convertV4MiniflareOptions({modules:true,script:'export default {fetch(){return new Response("ok")}}',d1Databases:['ES'],compatibilityDate:'2026-08-01'}));db=await runtime.getD1Database('ES') as unknown as D1Database;await db.exec(readFileSync('economysuite-migrations/0010_public_summary.sql','utf8'));});
 afterEach(async()=>{await runtime?.dispose();});
 it('returns unavailable before sync, expires at 30 seconds and clears disabled exports',async()=>{
  expect(await (await publicSummary(db,100)).json()).toMatchObject({fresh:false,server:null});
  await savePublicSnapshot(db,{version:1,enabled:true,server:{players:0,capacity:20},community:{active:true,progress:1,target:2,ends_at:120}},100);
  expect(await (await publicSummary(db,110)).json()).toMatchObject({fresh:true,server:{players:0},community:{progress:1}});
  expect(await (await publicSummary(db,130)).json()).toMatchObject({fresh:true,community:null});
  expect(await (await publicSummary(db,131)).json()).toMatchObject({fresh:false,server:null,community:null});
  await savePublicSnapshot(db,{version:1,enabled:false},132);expect(await (await publicSummary(db,132)).json()).toMatchObject({fresh:false,server:null});
  expect(await db.prepare('SELECT COUNT(*) n FROM public_server_snapshot').first('n')).toBe(1);
 });
 it('permits only anonymous GET to the exact public route and protects all existing routes',async()=>{
  const env={ECONOMYSUITE_DB:db} as Env,auth={authenticate:async()=>null,mutation:async()=>false};
  const request=(path:string,method='GET')=>new Request('https://account.pantheon.tomaspisar.cz/api/economysuite/'+path,{method});
  expect((await economySuite(request('public/summary'),env,auth)).status).toBe(200);
  expect((await economySuite(request('public/summary','POST'),env,auth)).status).toBe(405);
  for(const route of ['account','tournament','tournament/action','public/anything'])expect((await economySuite(request(route),env,auth)).status).toBe(401);
  expect((await economySuite(request('bridge/public/sync','POST'),{...env,ECONOMYSUITE_BRIDGE_SECRET:'a'.repeat(64)},auth)).status).toBe(403);
 });
});

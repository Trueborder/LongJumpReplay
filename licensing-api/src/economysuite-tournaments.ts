import type { Env } from './config';
import type { PlayerAuth } from './economysuite';
import { now, rateLimit } from './db';

type Obj = Record<string, unknown>;
const obj = (v: unknown): Obj => v && typeof v === 'object' && !Array.isArray(v) ? v as Obj : {};
const str = (v: unknown, max = 200) => typeof v === 'string' ? v.slice(0,max) : '';
const rows = (v: unknown, max: number): Obj[] => Array.isArray(v) ? v.slice(0,max).map(obj) : [];
const num = (v: unknown) => Number.isSafeInteger(v) && Number(v) >= 0 ? Number(v) : 0;
const UUID = /^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i;
const reply = (data: unknown, status = 200) => Response.json(data,{status,headers:{'Cache-Control':'no-store'}});
const fail = (message: string, status = 409) => reply({error:'tournament_error',message},status);
export const ADMIN_ACTIONS = ['create','advance','rules','pool','seeding','seed','automatic','time','add','remove','substitute','mode','arena','pause','recover','cleanup','cancel','forcewin','rematch','disqualify','prize','catalog_prize','remove_prize','clear_prizes','preset','announce'] as const;
export const CONFIRM_ACTIONS = new Set(['cancel','forcewin','rematch','disqualify','remove','substitute','remove_prize','clear_prizes','preset','announce']);
const identity = (v: unknown) => {const p=obj(v);return {uuid:UUID.test(str(p.uuid))?str(p.uuid):'',name:str(p.name,32),skin:skinUrl(p.skin),online:p.online===true,eligible:p.eligible===true,status:str(p.status),detail:str(p.detail,500),can_spectate:p.can_spectate===true};};
export function skinUrl(v: unknown): string {
  const value=str(v,180).replace(/^http:\/\//,'https://');
  return /^https:\/\/textures\.minecraft\.net\/texture\/[a-f0-9]{32,64}$/.test(value)?value:'';
}
/** Explicit bounded DTO; never expose serialized ItemStacks, addresses or account data. */
export function tournamentSnapshot(value: unknown): Obj {
  const v=obj(value);
  return {
    version:v.version===1?1:0,id:str(v.id,64),instance:str(v.instance,64),revision:num(v.revision),state:str(v.state,24),state_name:str(v.state_name,80),
    size:[2,4,8].includes(Number(v.size))?Number(v.size):8,best_of:v.best_of===3?3:1,policy:str(v.policy,16),mode:str(v.mode,40),round:num(v.round),
    created_at:num(v.created_at),server_time:num(v.server_time),deadline:num(v.deadline),automatic:v.automatic===true,random_seeding:v.random_seeding===true,celebrating:v.celebrating===true,
    players:rows(v.players,8).map(identity),waitlist:rows(v.waitlist,100).map(identity),online:rows(v.online,500).map(identity),
    matches:rows(v.matches,16).map(m=>({id:str(m.id,40),label:str(m.label,40),round:num(m.round),first:str(m.first,36),second:str(m.second,36),winner:str(m.winner,36),loser:str(m.loser,36),first_score:num(m.first_score),second_score:num(m.second_score),mode:str(m.mode,40),arena:str(m.arena,80),state:str(m.state,24),phase:str(m.phase,80),time:str(m.time,40)})),
    prizes:rows(v.prizes,500).map(p=>({place:num(p.place),index:num(p.index),description:str(p.description),icon:str(p.icon,80)})),summary:str(v.summary,500),
    modes:(Array.isArray(v.modes)?v.modes:[]).slice(0,100).map(m=>str(m,40)),arenas:(Array.isArray(v.arenas)?v.arenas:[]).slice(0,100).map(a=>str(a,80)),pool:(Array.isArray(v.pool)?v.pool:[]).slice(0,100).map(m=>str(m,40)),
    times:Object.fromEntries(['inter-match-delay-seconds','reconnect-grace-seconds','sudden-death-seconds','waiting-reminder-seconds'].map(k=>[k,num(obj(v.times)[k])])),
    problems:(Array.isArray(v.problems)?v.problems:[]).slice(0,100).map(p=>str(p)),
    presets:rows(v.presets,100).map(p=>({id:str(p.id,80),name:str(p.name,100),summary:str(p.summary,500)})),
    catalog_revision:str(v.catalog_revision,64),catalog:rows(v.catalog,1000).map(p=>({id:str(p.id,80),category:str(p.category,40),name:str(p.name),icon:str(p.icon,80),amount:num(p.amount)}))
  };
}
export async function tournamentAdmin(db: D1Database, player: PlayerAuth): Promise<boolean> {
  // Bind the verified existing owner account once. A recreated email account does not inherit access.
  if(player.credential&&player.customer.email.toLowerCase()==='xpisar10@gmail.com')await db.prepare("INSERT OR IGNORE INTO tournament_admins(customer_id,created_at) VALUES(?,?)").bind(player.customer.id,now()).run();
  return !!await db.prepare('SELECT customer_id FROM tournament_admins WHERE customer_id=?').bind(player.customer.id).first();
}
export async function tournamentBridge(db: D1Database, path: string, data: Obj): Promise<Response> {
  if(path.endsWith('/sync')) {
    const snap=tournamentSnapshot(data.snapshot);
    if(snap.version!==1||!UUID.test(str(snap.instance))||!['','DRAFT','REGISTRATION','LOCKED','ROUND_READY','ROUND_ACTIVE','INTERMISSION','PAUSED','COMPLETED','CANCELLED'].includes(str(snap.state)))return fail('Invalid snapshot.',400);
    const id=str(snap.id)||'current',at=now();
    await db.batch([
      db.prepare('INSERT INTO tournament_snapshots VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,revision=excluded.revision,synced_at=excluded.synced_at').bind('current',JSON.stringify(snap),snap.revision,at),
      ...(id!=='current'&&['COMPLETED','CANCELLED'].includes(str(snap.state))?[db.prepare('INSERT OR IGNORE INTO tournament_snapshots VALUES(?,?,?,?)').bind(id,JSON.stringify(snap),snap.revision,at)]:[]),
      db.prepare("UPDATE tournament_operations SET state='expired',result='Request expired; refresh and try again.',completed_at=? WHERE state='pending' AND expires_at<?").bind(at,at),
      db.prepare('DELETE FROM tournament_reauth WHERE expires_at<?').bind(at),
    ]);
    const operations=await db.prepare("SELECT o.* FROM tournament_operations o WHERE o.state='pending' AND o.expires_at>=? AND ((o.player_uuid IS NOT NULL AND EXISTS(SELECT 1 FROM player_links l WHERE l.customer_id=o.customer_id AND l.uuid=o.player_uuid)) OR (o.player_uuid IS NULL AND EXISTS(SELECT 1 FROM tournament_admins a WHERE a.customer_id=o.customer_id))) ORDER BY o.created_at,o.rowid LIMIT 8").bind(at).all<Obj>();
    return reply({operations:operations.results.map(o=>({...o,payload:JSON.parse(str(o.payload,20000))}))});
  }
  if(path.endsWith('/ack')) {
    await db.prepare("UPDATE tournament_operations SET state=?,result=?,completed_at=? WHERE id=? AND state='pending'").bind(data.success===true?'complete':'failed',str(data.message,500),now(),str(data.id,64)).run();
    return reply({acknowledged:true});
  }
  return fail('Not found.',404);
}
export async function tournamentRoute(request: Request, env: Env, db: D1Database, player: PlayerAuth, linkedUuid: string|null, data: Obj): Promise<Response> {
  const path=new URL(request.url).pathname,admin=await tournamentAdmin(db,player),at=now();
  const stored=await db.prepare("SELECT payload,synced_at FROM tournament_snapshots WHERE id='current'").first<{payload:string;synced_at:number}>();
  const snap=stored?tournamentSnapshot(JSON.parse(stored.payload)):null,fresh=!!stored&&at-stored.synced_at<=45&&snap?.version===1;
  if(request.method==='GET'&&path==='/api/economysuite/tournament') {
    await db.prepare("UPDATE tournament_operations SET state='expired',result='Request expired; refresh and try again.',completed_at=? WHERE state='pending' AND expires_at<?").bind(at,at).run();
    const history=await db.prepare("SELECT payload FROM tournament_snapshots WHERE id!='current' AND json_extract(payload,'$.state') IN ('COMPLETED','CANCELLED') ORDER BY synced_at DESC LIMIT 20").all<{payload:string}>();
    const operations=await db.prepare('SELECT id,action,state,result FROM tournament_operations WHERE customer_id=? ORDER BY created_at DESC,rowid DESC LIMIT 20').bind(player.customer.id).all();
    // Catalog, online roster and operational diagnostics are admin-only.
    const visible=(s:Obj)=>{const out={...s};if(!admin)for(const key of ['catalog','presets','online','problems','catalog_revision','times'])delete out[key];return out;};
    return reply({admin,fresh,synced_at:stored?.synced_at??null,server_time:at,uuid:linkedUuid,player_online:fresh&&rows(snap?.online,500).some(p=>p.uuid===linkedUuid&&p.eligible===true),snapshot:snap?visible(snap):null,history:history.results.map(r=>visible(tournamentSnapshot(JSON.parse(r.payload)))),operations:operations.results});
  }
  if(path!=='/api/economysuite/tournament/action'||request.method!=='POST')return fail('Not found.',404);
  const action=str(data.action,40),isPlayer=['join','leave'].includes(action);
  if(!isPlayer&&(!admin||!ADMIN_ACTIONS.includes(action as typeof ADMIN_ACTIONS[number])))return fail('Forbidden.',403);
  if(!UUID.test(str(data.idempotency_key,64)))return fail('Invalid operation ID.',400);
  const payload=obj(data.payload),id=str(data.idempotency_key,64),serialized=JSON.stringify(payload);
  if(serialized.length>12000||Object.values(payload).some(v=>typeof v==='string'&&v.length>1000))return fail('Invalid input.',400);
  const existing=await db.prepare('SELECT * FROM tournament_operations WHERE id=?').bind(id).first<Obj>();
  if(existing){if(existing.customer_id!==player.customer.id||existing.action!==action||existing.payload!==serialized)return fail('Operation ID conflict.');return reply({operation_id:id,state:existing.state});}
  if(!fresh||!snap)return fail('Server data is unavailable or stale.',503);
  if(str(data.tournament_id,64)!==snap.id||num(data.revision)!==snap.revision||str(data.instance,64)!==snap.instance)return fail('Tournament changed. Refresh and try again.');
  if(isPlayer){
    if(!linkedUuid)return fail('Pair your Minecraft account first.');
    if(!rows(snap.online,500).some(p=>p.uuid===linkedUuid&&p.eligible===true))return fail('Sign in to Minecraft first.');
    if(snap.state!=='REGISTRATION')return fail('Registration is closed.');
  }else{
    // The authenticated account's stable owner role is sufficient; no second password prompt.
    if(CONFIRM_ACTIONS.has(action)&&data.confirm!==true)return fail('Explicit confirmation required.',400);
  }
  if(!await rateLimit(env.DB,`es:tournament:action:${player.customer.id}`,60,30))return fail('Too many changes. Wait a moment.',429);
  // Capture the account's current link, never a browser supplied Minecraft UUID.
  const inserted=await db.prepare("INSERT OR IGNORE INTO tournament_operations(id,customer_id,player_uuid,action,payload,tournament_id,revision,instance,created_at,expires_at) VALUES(?,?,?,?,?,?,?,?,?,?)").bind(id,player.customer.id,isPlayer?linkedUuid:null,action,serialized,snap.id,snap.revision,snap.instance,at,at+15).run();
  return reply({operation_id:id,state:'pending'},inserted.meta.changes?202:200);
}

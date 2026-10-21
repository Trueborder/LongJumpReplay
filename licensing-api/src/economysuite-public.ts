/** Public allowlist. Never reuse authenticated player or tournament responses here. */
type Obj = Record<string, unknown>;
const obj = (v: unknown): Obj => v && typeof v === 'object' && !Array.isArray(v) ? v as Obj : {};
const text = (v: unknown, max = 120) => typeof v === 'string' ? v.replace(/(?:[&§][0-9a-fk-or]|[&§]#[0-9a-f]{6})/gi, '').replace(/[\u0000-\u001f\u007f]/g, '').slice(0,max) : '';
const integer = (v: unknown, max = Number.MAX_SAFE_INTEGER) => typeof v === 'number' && Number.isSafeInteger(v) && v >= 0 ? Math.min(v,max) : 0;
const states = new Set(['REGISTRATION','LOCKED','ROUND_READY','ROUND_ACTIVE','INTERMISSION','PAUSED']);
export function publicSnapshot(value: unknown) {
  const v=obj(value),server=obj(v.server),t=obj(v.tournament),c=obj(v.community);
  return {
    version:1,enabled:v.version===1&&v.enabled===true,
    server:{players:integer(server.players,100000),capacity:integer(server.capacity,100000),version:text(server.version,30),edition:'Java'},
    tournament:states.has(String(t.state))?{state:String(t.state),players:integer(t.players,8),size:[2,4,8].includes(Number(t.size))?Number(t.size):8,best_of:t.best_of===3?3:1,mode:text(t.mode,40),policy:['SAME','RANDOM','MANUAL'].includes(String(t.policy))?String(t.policy):'SAME',summary:text(t.summary,500)}:null,
    community:c.active===true?{active:true,title:text(c.title),progress:integer(c.progress),target:integer(c.target),ends_at:integer(c.ends_at)}:null
  };
}
export async function savePublicSnapshot(db:D1Database,value:unknown,at:number) {
  const payload=publicSnapshot(value);
  await db.prepare("INSERT INTO public_server_snapshot VALUES('pantheon',?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,synced_at=excluded.synced_at").bind(JSON.stringify(payload),at).run();
}
export async function publicSummary(db:D1Database,at:number):Promise<Response> {
  const row=await db.prepare("SELECT payload,synced_at FROM public_server_snapshot WHERE id='pantheon'").first<{payload:string;synced_at:number}>();
  let snapshot=publicSnapshot(null);try{if(row)snapshot=publicSnapshot(JSON.parse(row.payload));}catch{/* Corrupt/old data is unavailable, never speculative. */}
  const fresh=!!row&&snapshot.enabled&&at>=row.synced_at&&at-row.synced_at<=30;
  const community=snapshot.community;
  const availability=fresh?'live':!row?'waiting':!snapshot.enabled?'disabled':'stale';
  return Response.json({version:1,updated_at:row?.synced_at??null,fresh,availability,server:fresh?snapshot.server:null,tournament:fresh?snapshot.tournament:null,community:fresh&&community&&(community.ends_at===0||community.ends_at>at)&&community.progress<community.target?community:null},{headers:{'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}});
}

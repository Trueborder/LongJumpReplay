const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const path=require('node:path');
const root=path.join(__dirname,'../tomaspisar.cz/account/economysuite'),ui=require(path.join(root,'tournament.js'));
const t=(cs,en)=>cs;
const players=Array.from({length:8},(_,i)=>({uuid:'p'+i,name:i===0?'<script>':'Player'+i,skin:'https://textures.minecraft.net/texture/'+'a'.repeat(64)}));
test('brackets render 2/4/8 players, BO scores, bronze and escaped player names',()=>{
  for(const size of [2,4,8]){
    const matches=[];let count=size/2;for(let round=1;count>=1;round++,count/=2)for(let i=0;i<count;i++)matches.push({id:round+'-'+i,round,label:count===1?'Final':count===2?'Semifinal':'Quarterfinal',first:'p0',second:'p1',first_score:1,second_score:0,state:'RUNNING',mode:'Mace',arena:'Rocky'});
    if(size>2)matches.push({id:'bronze',round:3,label:'Bronze',first:'p2',second:'p3',state:'PENDING'});
    const result=ui.bracket({players,matches,best_of:3},t,'p0');assert.match(result,/BO3/);assert.match(result,/&lt;script&gt;/);assert.doesNotMatch(result,/<script>/);assert.match(result,/data-skin="https:\/\/textures.minecraft.net/);assert.match(result,/<canvas/);assert.match(result,/is-own/);if(size>2)assert.match(result,/tw-bronze/);
  }
});
test('head accepts only actual Mojang texture URLs and keeps a fallback',()=>{
  assert.equal(ui.skin('https://evil.example/skin.png'),'');assert.match(ui.head({name:'Adam',skin:'javascript:alert(1)'}),/>Ad<\/span>/);assert.doesNotMatch(ui.head({skin:'javascript:alert(1)'}),/javascript:/);
});
test('future bracket rounds are placeholders, never invented playable matches',()=>{
  const html=ui.bracket({size:8,players,matches:[{id:'q1',round:1,label:'Quarterfinal',first:'p0',second:'p1',state:'PENDING'}],best_of:1},t,'p0');
  assert.match(html,/FINÁLE|Finále/);assert.match(html,/tw-bronze/);assert.doesNotMatch(html,/data-match="pending-/);assert.match(html,/disabled/);
});
test('completed standings preserve shared fifth through eighth place',()=>{
  const results=ui.standings({state:'COMPLETED',players,matches:[{label:'Final',winner:'p0',loser:'p2'},{label:'Bronze',winner:'p4',loser:'p6'},...['p1','p3','p5','p7'].map(loser=>({label:'Quarterfinal',loser}))]});
  assert.deepEqual(results.map(p=>p.place),[1,2,3,4,5,5,5,5]);assert.equal(ui.standings({state:'ROUND_ACTIVE'}).length,0);
});
test('next phase never skips matches, transfer, intermission or ceremony',()=>{
  for(const state of ['LOCKED','INTERMISSION','ROUND_ACTIVE','COMPLETED'])assert.equal(ui.nextAction({id:'t',state,matches:[],problems:[]},t).disabled,true);
  assert.equal(ui.nextAction({id:'t',state:'ROUND_READY',matches:[],problems:['Blocked']},t).disabled,true);
  assert.equal(ui.nextAction({id:'t',state:'ROUND_READY',matches:[],problems:[]},t).disabled,false);
  assert.equal(ui.nextAction({id:'t',state:'DRAFT',celebrating:true,matches:[]},t).disabled,true);
});
test('admin panel uses typed operations, confirmations, no command editor and retains forms during polls',async()=>{
  const snapshot={id:'t',instance:'i',revision:1,state:'DRAFT',size:4,best_of:1,policy:'RANDOM',mode:'Mace',round:0,players:[],waitlist:[],online:[],matches:[],prizes:[],modes:['Mace'],pool:['Mace'],arenas:['rocky'],catalog:[],presets:[],times:{'inter-match-delay-seconds':30},problems:[]};
  await ui.load(async()=>({snapshot,admin:true,history:[],operations:[],server_time:1,fresh:true}));
  const html=ui.render({t,admin:true});assert.match(html,/data-tw-form="rules"/);assert.match(html,/data-stamp=/);assert.match(html,/value="30"/);assert.doesNotMatch(html,/tw-reauth|Příkazová odměna|name="command"/);
  const source=fs.readFileSync(path.join(root,'tournament.js'),'utf8');assert.match(source,/setInterval\(poll,2000\)/);assert.match(source,/form\.dataset\.stamp/);assert.match(source,/getContext\('2d'\)/);assert.match(source,/drawImage\(img,40\*unit/);
});

const fixture=overrides=>({id:'t',instance:'i',revision:1,state:'REGISTRATION',size:4,best_of:3,policy:'RANDOM',mode:'Mace',round:0,players:[{uuid:'p0',name:'Adam',online:true}],waitlist:[{uuid:'p1',name:'Tereza'}],online:[{uuid:'p0',name:'Adam'},{uuid:'p1',name:'Tereza'},{uuid:'p2',name:'Klarka'}],matches:[],prizes:[{place:1,index:0,description:'100 coinů'}],summary:'100C',modes:['Mace'],pool:['Mace'],arenas:['rocky'],catalog:[],presets:[],times:{'inter-match-delay-seconds':30},problems:[],...overrides});
async function renderFixture(admin,snapshot=fixture(),extra={}){
  await ui.load(async()=>({snapshot,admin:true,history:[],operations:[],server_time:1,fresh:true,uuid:'p0',player_online:false,...extra}));
  return ui.render({t,admin});
}
test('admin is settings only, with six compact sections and one player roster',async()=>{
  const html=await renderFixture(true);
  assert.doesNotMatch(html,/id="tw-live"|tw-bracket|id="tw-history"|TVŮJ TURNAJ/);
  assert.equal((html.match(/data-admin-section=/g)||[]).length,6);
  assert.equal((html.match(/data-player-row="p0"/g)||[]).length,1);
  assert.equal((html.match(/data-player-row="p1"/g)||[]).length,1);
  assert.match(html,/name="player" value="Adam"/);
  assert.match(html,/name="player" value="p0"/);
  assert.match(html,/name="replacement"><option value="Klarka"/);
  assert.doesNotMatch(html,/name="replacement"><option value="Adam"/);
  assert.match(html,/aria-controls="tw-section-players"/);
  assert.match(html,/<fieldset class="tw-mode-pool">/);
  assert.match(html,/type="checkbox" name="modes" value="Mace" checked/);
  assert.doesNotMatch(html,/módy oddělené čárkou/);
});
test('creation gates every reward action and preserves current config times',async()=>{
  const html=await renderFixture(true,fixture({id:'',state:'DRAFT',times:{'inter-match-delay-seconds':45}}));
  assert.match(html,/value="45"/);
  assert.match(html,/data-tw-form="create"/);
  assert.match(html,/Nejprve vytvoř turnaj/);
  for(const action of ['prize','catalog_prize','preset','clear_prizes','time']){
    const form=html.match(new RegExp('<form[^>]*data-tw-form="'+action+'"[\\s\\S]*?<\/form>'))?.[0];
    assert.match(form||'',/<button type="submit" disabled>/,action);
  }
});
test('match controls bind one concrete match and offer only its two opponents',async()=>{
  const s=fixture({players:[...players.slice(1,4)],matches:[{id:'m1',first:'p1',second:'p2',state:'PENDING',label:'Final',mode:'Mace'}]});
  const html=await renderFixture(true,s);
  const forced=html.match(/data-tw-form="forcewin"[\s\S]*?<\/form>/)?.[0];
  assert.match(forced,/name="match" value="m1"/);assert.match(forced,/Player1/);assert.match(forced,/Player2/);assert.doesNotMatch(forced,/Player3/);
});
test('unauthorized admin has no controls, while public tournament keeps bracket and folds secondary data',async()=>{
  const denied=await renderFixture(true,fixture(),{admin:false});assert.doesNotMatch(denied,/data-tw-form|data-admin-section/);
  const html=await renderFixture(false,fixture(),{uuid:'not-enrolled'});
  assert.match(html,/id="tw-live"/);assert.match(html,/tw-arena/);assert.match(html,/data-disclosure="history"/);
  assert.doesNotMatch(html,/Pro registraci nejprve propoj účet/);assert.match(html,/Pro registraci se přihlas v Minecraftu/);
  assert.doesNotMatch(html,/tw-operation-log/);
});
test('navigation places tournaments directly above Settings and motion preserves keyboard and reduced-motion paths',()=>{
  const app=fs.readFileSync(path.join(root,'app.js'),'utf8'),css=fs.readFileSync(path.join(root,'app.css'),'utf8');
  assert.match(app,/'tournament','tournament-admin','settings'/);
  assert.match(css,/\.tw-dialog\{opacity:0;transform:scale\(\.96\);transition:opacity 200ms var\(--ease-out\)/);
  assert.match(css,/html\[data-motion-input=keyboard\] \.tw-dialog/);
  assert.match(css,/@media\(prefers-reduced-motion:reduce\)\{\.tw-dialog/);
  assert.match(css,/@starting-style/);
});
test('reward suggestions match Czech names without accents, all query words and categories',async()=>{
  const catalog=[{id:'key',name:'&6Legendární klíč',category:'keys'},{id:'other',name:'Legendární meč',category:'items'},{id:'html',name:'<img src=x>',category:'items'}];
  assert.deepEqual(ui.catalogMatches(catalog,'leg klic').map(p=>p.id),['key']);
  assert.deepEqual(ui.catalogMatches(catalog,'LEGENDÁRNÍ','items').map(p=>p.id),['other']);
  assert.equal(ui.catalogMatches(catalog,'nenalezeno').length,0);
  const html=await renderFixture(true,fixture({catalog}));
  assert.match(html,/aria-controls="tw-reward-suggestions"/);assert.match(html,/id="tw-reward-suggestions"/);
  assert.doesNotMatch(html,/<img src=x>/);assert.doesNotMatch(html,/reauth|type="password"/);
  const source=fs.readFileSync(path.join(root,'tournament.js'),'utf8');assert.doesNotMatch(source,/reauth_token|\/reauth|Ověř heslo/);
});
test('action colours follow meaning, including the selected currency',()=>{
  for(const action of ['cancel','remove','remove_prize','clear_prizes','disqualify'])assert.equal(ui.buttonTone(action),'danger');
  assert.equal(ui.buttonTone('pause'),'warning');assert.equal(ui.buttonTone('prize',{type:'coins'}),'coins');assert.equal(ui.buttonTone('prize',{type:'tokens'}),'tokens');
  assert.equal(ui.buttonTone('add'),'success');assert.equal(ui.buttonTone('time'),'info');assert.equal(ui.buttonTone('catalog_prize'),'accent');
});
test('disabled controls explain missing setup, locked rules, empty rewards and seeding limits in both languages',()=>{
  const s=fixture();
  assert.match(ui.unavailableReason('prize',{...s,id:''}),/vytvoř nový turnaj/);
  assert.match(ui.unavailableReason('rules',{...s,state:'ROUND_ACTIVE'}),/Registrace je uzamčená/);
  assert.match(ui.unavailableReason('seed',s,{player:'p0',direction:-1}),/prvním místě/);
  assert.match(ui.unavailableReason('seed',s,{player:'p0',direction:1}),/posledním místě/);
  assert.match(ui.unavailableReason('substitute',{...s,online:[]}),/Není dostupný/);
  assert.match(ui.unavailableReason('catalog_prize',s),/vyhledávání/);
  assert.match(ui.unavailableReason('preset',s),/preset/);
  assert.match(ui.unavailableReason('advance',{...s,state:'INTERMISSION'}),/povinná pauza/);
  assert.match(ui.unavailableReason('advance',{...s,state:'ROUND_READY',problems:['Rocky: neplatný spawn B']}),/neplatný spawn B/);
  assert.match(ui.unavailableReason('rules',{...s,state:'ROUND_ACTIVE'},{},(cs,en)=>en),/Registration is locked/);
  const source=fs.readFileSync(path.join(root,'tournament.js'),'utf8');
  assert.match(source,/aria-describedby/);assert.match(source,/pointerenter/);assert.match(source,/focusin/);assert.match(source,/hintSequence/);assert.match(source,/e.key==='Escape'/);
});

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
  const html=ui.render({t,admin:true});assert.match(html,/data-tw-form="rules"/);assert.match(html,/data-stamp=/);assert.match(html,/value="30"/);assert.match(html,/tw-reauth/);assert.doesNotMatch(html,/Příkazová odměna|name="command"/);
  const source=fs.readFileSync(path.join(root,'tournament.js'),'utf8');assert.match(source,/setInterval\(poll,2000\)/);assert.match(source,/form\.dataset\.stamp/);assert.match(source,/getContext\('2d'\)/);assert.match(source,/drawImage\(img,40\*unit/);
});

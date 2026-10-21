const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const base=path.resolve(__dirname,'../shared/pantheon');
const code=fs.readFileSync(path.join(base,'theme.js'),'utf8');
function boot({host='pantheon.tomaspisar.cz',dark=false,cookie='',local=null,denied=false,marked=false}={}){
 const docEvents={},windowEvents={},mediaEvents={},storage=new Map(local?[['pantheon-theme',local]]:[]),writes=[];
 const root={lang:'cs',dataset:{},hasAttribute:()=>marked,setAttribute(){marked=true;}};
 const selects=[1,2].map(()=>({value:'',options:['system','light','dark'].map(value=>({value,textContent:''})),setAttribute(key,value){this[key]=value;},matches:selector=>selector==='[data-pt-theme]'}));
 const labels=[{textContent:''}],media={matches:dark,addEventListener:(name,fn)=>mediaEvents[name]=fn};
 let observer;
 const document={documentElement:root,hidden:false,querySelectorAll:selector=>selector==='[data-pt-theme]'?selects:labels,addEventListener:(name,fn)=>docEvents[name]=fn};
 Object.defineProperty(document,'cookie',{get(){if(denied)throw Error('blocked');return cookie;},set(value){if(denied)throw Error('blocked');writes.push(value);cookie=value.split(';')[0];}});
 const window={matchMedia:()=>media,addEventListener:(name,fn)=>windowEvents[name]=fn};
 const localStorage={getItem:key=>{if(denied)throw Error('blocked');return storage.get(key)||null;},setItem:(key,value)=>{if(denied)throw Error('blocked');storage.set(key,value);}};
 vm.runInNewContext(code,{document,window,location:{hostname:host,protocol:'https:'},localStorage,MutationObserver:class{constructor(fn){observer=fn;}observe(){}}});
 return {root,selects,labels,media,writes,storage,docEvents,windowEvents,change:value=>docEvents.change({target:{...selects[0],value}}),system:value=>{media.matches=value;mediaEvents.change();},setCookie:value=>cookie=value,language:lang=>{root.lang=lang;observer();}};
}
test('system is the default and follows device changes without writing a preference',()=>{
 const app=boot({dark:true});assert.equal(app.root.dataset.pantheonPreference,'system');assert.equal(app.root.dataset.theme,'dark');assert.equal(app.selects[1].value,'system');assert.equal(app.writes.length,0);app.system(false);assert.equal(app.root.dataset.pantheonTheme,'light');
});
test('explicit theme persists to the Pantheon parent domain and synchronizes both controls',()=>{
 const app=boot({host:'account.pantheon.tomaspisar.cz'});app.change('dark');assert.equal(app.root.dataset.theme,'dark');assert.equal(app.storage.get('pantheon-theme'),'dark');assert.match(app.writes[0],/Domain=pantheon\.tomaspisar\.cz/);assert.match(app.writes[0],/SameSite=Lax/);assert.match(app.writes[0],/Secure/);assert.equal(app.selects[1].value,'dark');app.system(false);assert.equal(app.root.dataset.theme,'dark');app.change('system');app.system(true);assert.equal(app.root.dataset.theme,'dark');
});
test('cookie preference wins across subdomains and is refreshed when returning to a tab',()=>{
 const app=boot({cookie:'other=1; pantheon-theme=dark',local:'light'});assert.equal(app.root.dataset.theme,'dark');app.setCookie('pantheon-theme=light');app.windowEvents.focus();assert.equal(app.root.dataset.theme,'light');
});
test('invalid saved values are rejected and blocked storage does not break the controls',()=>{
 const invalid=boot({cookie:'pantheon-theme=javascript:bad',local:'unknown'});assert.equal(invalid.root.dataset.pantheonPreference,'system');invalid.change('bad');assert.equal(invalid.writes.length,0);
 const blocked=boot({denied:true});blocked.change('dark');assert.equal(blocked.root.dataset.theme,'dark');blocked.windowEvents.focus();assert.equal(blocked.root.dataset.theme,'dark');
});
test('theme labels follow account language without changing the selected preference',()=>{
 const app=boot();app.change('dark');app.language('en');assert.equal(app.labels[0].textContent,'Theme');assert.equal(app.selects[0].options[2].textContent,'Dark');assert.equal(app.selects[0]['aria-label'],'Color theme');assert.equal(app.selects[1].value,'dark');
});
test('unrelated account hosts do not opt into Pantheon styling or preference behavior',()=>{
 const app=boot({host:'ljr.tomaspisar.cz'});assert.deepEqual(app.root.dataset,{});assert.equal(Object.keys(app.docEvents).length,0);const local=boot({host:'localhost',marked:true});assert.equal(local.root.dataset.theme,'light');
});
test('account distributes the exact shared assets and dark palette is defined separately',()=>{
 const target=path.resolve(__dirname,'../tomaspisar.cz/account/pantheon');for(const file of fs.readdirSync(base))assert.deepEqual(fs.readFileSync(path.join(target,file)),fs.readFileSync(path.join(base,file)),file);
 const css=fs.readFileSync(path.join(base,'design.css'),'utf8');assert.match(css,/data-pantheon-theme=dark/);assert.match(css,/color-scheme:dark/);assert.match(css,/--pt-danger-bg/);assert.match(css,/font-display:swap/);
});

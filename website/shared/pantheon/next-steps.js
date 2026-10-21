/* Read-only suggestions derived exclusively from the existing player snapshot. */
(function(scope){
 'use strict';
 function actions(account,events,level,lang='cs',now=Date.now()/1000){
  const cs=lang==='cs',t=(a,b)=>cs?a:b,snapshot=account?.snapshot;
  if(!account?.link||!snapshot)return [];
  const items=[];
  if(events?.fresh===true&&Number.isFinite(events.updated_at)&&Math.abs(now-events.updated_at)<=30&&events.tournament?.state==='REGISTRATION')items.push({id:'tournament',title:t('Registrace do turnaje je otevřená','Tournament registration is open'),detail:account.server_online&&snapshot.online?t('Otevři turnaj a zkontroluj podmínky přihlášení.','Open the tournament and check entry requirements.'):t('Přihláška vyžaduje připojeného a přihlášeného hráče ve hře.','Entry requires you to be connected and signed in to the game.'),href:'/economysuite/tournament',guide:'/duely-a-turnaje'});
  if(!snapshot.job?.id)items.push({id:'job',title:t('Vyber si první profesi','Choose your first job'),detail:t('Ve hře otevři /jobs a vyber si činnost, která tě baví.','Open /jobs in the game and choose an activity you enjoy.'),href:'/economysuite/progress',guide:'/ukoly-povolani-a-postup'});
  const recent=account.server_online===true&&Number.isFinite(account.synced_at)&&now-account.synced_at<=60&&account.synced_at<=now+30;
  const tasks=recent&&snapshot.progress?.tasks_version===2?['daily','weekly'].flatMap(period=>(Array.isArray(snapshot.progress[period])?snapshot.progress[period]:[]).filter(task=>!task.complete&&Number.isFinite(task.target)&&task.target>0&&Number.isFinite(task.progress)&&task.progress>=0&&task.progress<task.target).map(task=>({...task,period}))):[];
  tasks.sort((a,b)=>b.progress/b.target-a.progress/a.target);
  for(const task of tasks.slice(0,2))items.push({id:'task-'+task.period+'-'+task.id,title:String(task.name||task.id||t('Úkol','Task')),detail:(task.period==='daily'?t('Denní úkol','Daily task'):t('Týdenní úkol','Weekly task'))+' · '+task.progress.toLocaleString(lang)+' / '+task.target.toLocaleString(lang)+' · '+t('Pokračuj ve hře přes /tasks.','Continue in-game with /tasks.'),href:'/economysuite/progress',guide:'/ukoly-povolani-a-postup'});
  if(level&&level.current<100)items.push({id:'level',title:t('Další cíl: level ','Next goal: level ')+(level.current+1),detail:level.remaining.toLocaleString(lang)+t(' XP do dalšího levelu. XP získáváš hraním.',' XP to the next level. Earn XP by playing.'),href:'/economysuite/progress',guide:'/ukoly-povolani-a-postup'});
  if(!items.length)items.push({id:'explore',title:t('Najdi další cíl ve hře','Find your next in-game goal'),detail:t('Prohlédni sbírky, odměny a svoje dosažené výsledky.','Explore collections, rewards and your achievements.'),href:'/economysuite/progress',guide:'/kniha-sbirek'});
  return items.slice(0,5);
 }
 const api={actions};if(typeof module!=='undefined'&&module.exports)module.exports=api;else scope.PantheonNext=api;
})(typeof window!=='undefined'?window:{});

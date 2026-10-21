/* Keep the existing consent controls and choices; localize only their presentation. */
(()=>{
 if(!document.documentElement.hasAttribute('data-pantheon-brand'))return;
 const update=()=>{
  const cs=document.documentElement.lang==='cs';
  for(const banner of document.querySelectorAll('.consent-dialog,.cookie-banner')){
   const copy=cs?'Web si pamatuje zvolený jazyk a barevný motiv. Nepoužívá analytické ani reklamní cookies. ':'The site remembers your chosen language and appearance. It uses no analytics or advertising cookies. ';
   const paragraph=banner.querySelector('p');
   if(paragraph?.firstChild?.nodeType===3&&paragraph.firstChild.textContent!==copy)paragraph.firstChild.textContent=copy;
   for(const [selector,text]of [['.button-outline',cs?'Odmítnout':'Decline'],['.button-primary',cs?'Přijmout':'Accept']]){const button=banner.querySelector(selector);if(button&&button.textContent!==text)button.textContent=text;}
   const more=banner.querySelector('a');const label=cs?'Soukromí →':'Privacy →';if(more&&more.textContent!==label)more.textContent=label;
   banner.setAttribute('aria-label',cs?'Volby cookies':'Cookie choices');
  }
 };
 new MutationObserver(update).observe(document.body,{childList:true,subtree:true});
 new MutationObserver(update).observe(document.documentElement,{attributes:true,attributeFilter:['lang']});update();
})();

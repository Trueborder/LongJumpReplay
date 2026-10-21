/* Brand the existing shared authentication form without changing its behavior. */
(() => {
  if (!document.documentElement.hasAttribute('data-pantheon-brand')) return;
  document.querySelectorAll('.login-home-link').forEach(link => {
    link.href='https://pantheon.tomaspisar.cz/';
    link.setAttribute('aria-label','Pantheon Survival');
    link.classList.add('pt-brand');
    const image=link.querySelector('img');if(image)image.src='/pantheon/temple.svg';
    if(!link.querySelector('.pt-auth-brand-text')){const text=document.createElement('span');text.className='pt-auth-brand-text';text.textContent='PANTHEON';link.append(text);}
  });
  const bar=document.querySelector('.login-card-bar');
  if(bar){
    const label=document.createElement('label');label.className='pt-theme-control';
    const caption=document.createElement('span');caption.dataset.ptThemeLabel='';caption.textContent='Motiv';
    const select=document.createElement('select');select.dataset.ptTheme='';select.setAttribute('aria-label','Barevný motiv');
    for(const [value,text] of [['system','Systém'],['light','Světlý'],['dark','Tmavý']]){const option=document.createElement('option');option.value=value;option.textContent=text;select.append(option);}
    label.append(caption,select);bar.append(label);
  }
  const card=document.querySelector('.login-card,.register-card');
  if(card){const nav=document.createElement('nav');nav.className='pt-auth-links';nav.setAttribute('aria-label','Pantheon');
    for(const [href,cs,en] of [['https://pantheon.tomaspisar.cz/','Server','Home'],['https://wiki.pantheon.tomaspisar.cz/','Wiki','Wiki'],['https://wiki.pantheon.tomaspisar.cz/zacni-tady','Začni tady','Start here']]){const link=document.createElement('a');link.href=href;link.dataset.cs=cs;link.dataset.en=en;link.textContent=document.documentElement.lang==='cs'?cs:en;nav.append(link);}
    const note=document.createElement('p');note.className='pt-auth-note';note.dataset.cs='Na webu používáš e-mail a heslo. Herní PIN zadávej pouze v Minecraftu. Propojení začneš příkazem /web link ve hře.';note.dataset.en='Use email and password on the website. Enter your game PIN only in Minecraft. Start linking with /web link in the game.';note.textContent=document.documentElement.lang==='cs'?note.dataset.cs:note.dataset.en;card.append(note);
    card.append(nav);
  }
})();

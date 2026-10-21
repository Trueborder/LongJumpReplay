import {afterEach,describe,expect,it} from 'vitest';
import {Miniflare,convertV4MiniflareOptions} from 'miniflare';
import {pantheonAuthBrand} from './pantheon-brand';

describe('Pantheon auth presentation wrapper',()=>{
 let runtime:Miniflare|undefined;
 afterEach(async()=>{await runtime?.dispose();});
 it('brands only presentation and preserves form fields, scripts, status and headers',async()=>{
  const html='<!doctype html><html lang="cs"><head><link rel="icon" href="old.png"><link rel="stylesheet" href="shared.css"></head><body><form id="login-form"><input id="email" name="email"><input id="password" name="password" type="password"><input id="code" name="code"></form><script src="account.js"></script></body></html>';
  const source=`${pantheonAuthBrand.toString()}; export default {fetch(){return pantheonAuthBrand(new Response(${JSON.stringify(html)},{status:200,headers:{'Content-Type':'text/html','Cache-Control':'no-store','X-Test':'preserved'}}));}}`;
  runtime=new Miniflare(convertV4MiniflareOptions({modules:true,script:source,compatibilityDate:'2026-08-01'}));
  const response=await runtime.dispatchFetch('https://account.pantheon.tomaspisar.cz/login');
  const body=await response.text();
  expect(response.status).toBe(200);expect(response.headers.get('Cache-Control')).toBe('no-store');expect(response.headers.get('X-Test')).toBe('preserved');
  expect(body).toContain('data-pantheon-brand');expect(body).toContain('/pantheon/theme.js');expect(body).toContain('/pantheon/auth.css');expect(body).toContain('/pantheon/temple.svg');
  expect(body.indexOf('/pantheon/theme.js')).toBeLessThan(body.indexOf('shared.css'));expect(body.indexOf('/pantheon/auth.css')).toBeGreaterThan(body.indexOf('shared.css'));
  for(const field of ['email','password','code'])expect(body).toContain(`id="${field}" name="${field}"`);
  expect(body).toContain('<script src="account.js"></script>');
 });
});

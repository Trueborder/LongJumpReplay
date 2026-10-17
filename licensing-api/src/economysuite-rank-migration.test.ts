/// <reference types="node" />
import { it,expect } from 'vitest';
import { Miniflare,convertV4MiniflareOptions } from 'miniflare';
import {readFileSync,readdirSync} from 'node:fs';
it('preserves existing orders, consent evidence and foreign keys while adding rank products',async()=>{
  const runtime=new Miniflare(convertV4MiniflareOptions({modules:true,script:'export default {fetch(){return new Response("ok")}}',d1Databases:['ES'],compatibilityDate:'2026-08-01'}));
  try{
    const db=await runtime.getD1Database('ES');
    for(const file of readdirSync('economysuite-migrations').filter(f=>f.endsWith('.sql')&&f<'0007').sort())await db.exec(readFileSync('economysuite-migrations/'+file,'utf8').replace(/--[^\n]*/g,'').split(/;(?!\s*END\b)/i).map(s=>s.replace(/\r?\n/g,' ').trim()).filter(Boolean).join(';\n')+';');
    await db.exec("INSERT INTO store_orders(id,customer_id,uuid,player_name,price_id,currency_type,currency_amount,price_minor,created_at,updated_at) VALUES('old','customer','uuid','Player','price','tokens',10,3900,1,1);");
    await db.exec("INSERT INTO purchase_consents(id,order_id,customer_id,accepted_at,policy_version,terms_version,refund_version,delivery_version,immediate_delivery_requested,withdrawal_rights_acknowledged,product_id,product_name,displayed_price_minor,displayed_currency,vat_notice) VALUES('consent','old','customer',1,'v','v','v','v',1,1,'price','Tokens',3900,'czk','notice');");
    const sql=readFileSync('economysuite-migrations/0007_supporter_ranks.sql','utf8').replace(/--[^\n]*/g,'');
    await db.batch(sql.split(';').map(s=>s.trim()).filter(Boolean).map(s=>db.prepare(s)));
    expect(await db.prepare('SELECT currency_amount FROM store_orders WHERE id=?').bind('old').first('currency_amount')).toBe(10);
    expect(await db.prepare('SELECT order_id FROM purchase_consents').first('order_id')).toBe('old');
    expect((await db.prepare('PRAGMA foreign_key_check').all()).results).toHaveLength(0);
    await db.prepare("INSERT INTO store_orders(id,customer_id,uuid,player_name,price_id,currency_type,currency_amount,price_minor,created_at,updated_at,product_type,rank_id) VALUES('new','customer','uuid','Player','rank_price','rank',604800,3900,1,1,'rank','vip')").run();
    expect(await db.prepare('SELECT COUNT(*) n FROM store_orders').first('n')).toBe(2);
  }finally{await runtime.dispose();}
},30000);

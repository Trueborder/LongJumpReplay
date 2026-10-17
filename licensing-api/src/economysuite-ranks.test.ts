import { describe, expect, it } from 'vitest';
import { packageFromProduct, targetCurrency } from './economysuite';
import { rankDelivery, rankProduct, RANK_WEEK_SECONDS } from './economysuite-ranks';
describe('supporter rank products',()=>{
  const metadata={es_product:'economysuite',es_server:'pantheon',es_published:'true',es_kind:'rank',es_rank:'vip'};
  const price={id:'price_rank',active:true,currency:'czk',type:'one_time',unit_amount:3900,metadata:{es_duration_seconds:'604800'}};
  it('recognizes rank products without converting them into virtual currency',()=>{expect(packageFromProduct({active:true,name:'VIP',metadata,default_price:price})).toMatchObject({currency:'rank',product_type:'rank',rank_id:'vip',amount:RANK_WEEK_SECONDS,price_minor:3900});});
  it('rejects unknown ranks, wrong weekly duration and unexpected prices',()=>{expect(rankProduct({...metadata,es_rank:'admin'},price)).toBeNull();expect(rankProduct(metadata,{...price,unit_amount:100})).toBeNull();expect(rankProduct(metadata,{...price,metadata:{es_duration_seconds:'1'}})).toBeNull();});
  it('fulfills with the original paid timestamp and bounded cumulative refund duration',()=>{expect(rankDelivery({id:'order',rank_id:'mvp'},1000,2000,targetCurrency(RANK_WEEK_SECONDS,9900,4950,''),2)).toEqual({order_id:'order',rank:'mvp',paid_at:1000000,effective_at:2000000,duration_seconds:302400,revision:2});expect(()=>rankDelivery({id:'order',rank_id:'admin'},1000,2000,604800,1)).toThrow();});
});

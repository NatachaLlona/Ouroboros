import { Api, ApiError } from './api';
import { CataloguePage, CatalogueRecord } from '../catalogue/resources';

/** Approve only a complete, deterministic paginated list; never expose a partial selection set. */
export async function readCataloguePages(api:Api,path:string,key:string,params:Record<string,string|number>,current:()=>boolean=()=>true):Promise<CatalogueRecord[]>{
  const records:CatalogueRecord[]=[],seen=new Set<string>();let expected:number|undefined;
  for(let page=1;;page++){
    if(!current())return [];
    const response=await api.request<CataloguePage>(path,'GET',undefined,undefined,{...params,page,page_size:50},false);
    if(!current())return [];
    if(!Number.isSafeInteger(response.count)||response.count<0||response.page!==page||response.page_size!==50||!Array.isArray(response.items))throw new ApiError(502);
    if(expected===undefined)expected=response.count;
    if(response.count!==expected||response.items.length!==Math.min(50,Math.max(0,expected-records.length)))throw new ApiError(502);
    for(const record of response.items){const id=record[key];if(typeof id!=='string'||!id||seen.has(id))throw new ApiError(502);seen.add(id);records.push(record);}
    if(records.length===expected)return records;
  }
}

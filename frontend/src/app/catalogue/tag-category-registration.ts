import { Injectable, computed, inject, signal } from '@angular/core';
import { Api, ApiError } from '../shared/api';
import { readCataloguePages } from '../shared/catalogue-pages';
import { uniqueSelectValues } from '../shared/select-options';
import { CatalogueRecord, recordId } from './resources';

/** Component-scoped receipt for the existing, separate tag/relationship transactions. */
@Injectable()
export class TagCategoryRegistration {
  private readonly api=inject(Api);private record:CatalogueRecord|null=null;
  private readonly attemptedCategories=new Set<string>();
  readonly created=signal(false);readonly uncertain=signal(false);readonly pending=computed(()=>this.created()||this.uncertain());
  reset():void{this.record=null;this.attemptedCategories.clear();this.created.set(false);this.uncertain.set(false);}

  private async relationships(id:string):Promise<CatalogueRecord[]>{
    const rows=await readCataloguePages(this.api,'/tag_category_relationships','id_tag_category_relationships',{id_tags:id,order_by:'id_tag_category_relationships',order_direction:'asc'});
    const categories=new Set<string>();
    for(const row of rows){const category=row['id_tag_categories'];if(row['id_tags']!==id||typeof category!=='string'||categories.has(category))throw new ApiError(502);categories.add(category);}
    return rows;
  }

  async save(body:CatalogueRecord,categories:readonly string[],csrf:string|undefined):Promise<CatalogueRecord>{
    if(this.uncertain())throw new ApiError(0,'',[],'','','/tags','POST');
    const selected=uniqueSelectValues(categories),desired=new Set(selected);
    if(!this.record){
      try{
        const record=await this.api.request<CatalogueRecord>('/tags','POST',body,csrf);
        if(!recordId('tags',record)||typeof record['display_name_tags']!=='string')throw new ApiError(502,'',[],'','','/tags','POST');
        this.record={...body,...record};this.created.set(true);
      }catch(error){
        // No idempotency key exists: an unknown tag-create result must never be replayed blindly.
        if(!(error instanceof ApiError)||error.status===0||error.status>=500)this.uncertain.set(true);
        throw error;
      }
    }else{
      // Corrections after relationship failure target the known tag, never another POST /tags.
      const changes=Object.fromEntries(Object.entries(body).filter(([key,value])=>this.record![key]!==value));
      if(Object.keys(changes).length){
        const record=await this.api.request<CatalogueRecord>('/tags/'+encodeURIComponent(recordId('tags',this.record)),'PUT',changes,csrf);
        if(recordId('tags',record)!==recordId('tags',this.record))throw new ApiError(502);
        this.record={...this.record,...changes,...record};
      }
    }
    const id=recordId('tags',this.record!);
    // With no selected/attempted categories, retain ordinary tag creation as one request.
    if(!selected.length&&!this.attemptedCategories.size)return this.record!;
    const existing=await this.relationships(id),linked=new Set(existing.map(row=>row['id_tag_categories'] as string));
    for(const relation of existing){
      const category=relation['id_tag_categories'] as string;
      if(this.attemptedCategories.has(category)&&!desired.has(category)){
        // Only links attempted by this unfinished creation flow may be removed by Clear All/correction.
        await this.api.request('/tag_category_relationships/'+encodeURIComponent(relation['id_tag_category_relationships'] as string),'DELETE',undefined,csrf);
        linked.delete(category);
      }
    }
    for(const category of selected){
      if(linked.has(category))continue;
      this.attemptedCategories.add(category);
      try{
        await this.api.request('/tag_category_relationships','POST',{id_tags:id,id_tag_categories:category},csrf);
      }catch(error){
        // A concurrent/repeated pair may already exist. Read to confirm; never retry the POST automatically.
        if(!(error instanceof ApiError)||error.status!==409)throw error;
        if(!(await this.relationships(id)).some(row=>row['id_tag_categories']===category))throw error;
      }
      linked.add(category);
    }
    return this.record!;
  }
}

import { Injectable, computed, inject, signal } from '@angular/core';
import { Api, ApiError } from '../shared/api';
import { readCataloguePages } from '../shared/catalogue-pages';
import { uniqueSelectValues } from '../shared/select-options';
import { CatalogueRecord, recordId, registrationDefinitions } from './resources';
import { TagCategoryOwner, tagCategoryAssociations } from './tag-category-association';

/** Component-scoped receipt and association snapshot shared by both forms. */
@Injectable()
export class TagCategoryRegistration {
  private readonly api=inject(Api);private record:CatalogueRecord|null=null;
  private owner:TagCategoryOwner|null=null;private readonly attemptedRelatedIds=new Set<string>();
  private editing=false;private initialRelatedIds=new Set<string>();private readonly editPending=signal(false);
  private recordUncertain=false;private readonly attemptedFields=new Set<string>();
  readonly created=signal(false);readonly uncertain=signal(false);readonly pending=computed(()=>this.created()||this.uncertain()||this.editPending());
  reset():void{this.record=null;this.owner=null;this.editing=false;this.recordUncertain=false;this.attemptedFields.clear();this.initialRelatedIds.clear();this.attemptedRelatedIds.clear();this.created.set(false);this.uncertain.set(false);this.editPending.set(false);}

  private async relationships(id:string,owner:TagCategoryOwner,current:()=>boolean=()=>true):Promise<CatalogueRecord[]>{
    const selection=tagCategoryAssociations[owner];
    const rows=await readCataloguePages(this.api,'/tag_category_relationships','id_tag_category_relationships',{[selection.ownerKey]:id,order_by:'id_tag_category_relationships',order_direction:'asc'},current);
    const relatedIds=new Set<string>();
    for(const row of rows){const related=row[selection.relatedKey];if(row[selection.ownerKey]!==id||typeof related!=='string'||relatedIds.has(related))throw new ApiError(502);relatedIds.add(related);}
    return rows;
  }

  async loadExisting(record:CatalogueRecord,owner:TagCategoryOwner,current:()=>boolean=()=>true):Promise<string[]>{
    const id=recordId(owner,record);if(!id)throw new ApiError(502);
    const rows=await this.relationships(id,owner,current);if(!current())return [];
    const ids=rows.map(row=>row[tagCategoryAssociations[owner].relatedKey] as string);
    this.reset();this.owner=owner;this.record={...record};this.editing=true;this.initialRelatedIds=new Set(ids);
    return ids;
  }

  private finish(selected:readonly string[]):CatalogueRecord{
    if(this.editing)this.initialRelatedIds=new Set(selected);
    this.attemptedFields.clear();this.editPending.set(false);return this.record!;
  }

  async save(body:CatalogueRecord,relatedIds:readonly string[],csrf:string|undefined,owner:TagCategoryOwner='tags',original?:CatalogueRecord,initialSelection:readonly string[]=[]):Promise<CatalogueRecord>{
    if(this.owner&&this.owner!==owner)throw new ApiError(400);
    this.owner=owner;
    const selection=tagCategoryAssociations[owner],path='/'+owner,display=registrationDefinitions[owner].display;
    if(original){
      const id=recordId(owner,original);if(!id)throw new ApiError(502);
      if(this.record&&(!this.editing||recordId(owner,this.record)!==id))throw new ApiError(400);
      if(!this.record){this.record={...original};this.editing=true;this.initialRelatedIds=new Set(initialSelection);}
    }
    if(this.uncertain())throw new ApiError(0,'',[],'','',path,'POST');
    const selected=uniqueSelectValues(relatedIds),desired=new Set(selected);
    if(!this.record){
      try{
        const record=await this.api.request<CatalogueRecord>(path,'POST',body,csrf);
        if(!recordId(owner,record)||typeof record[display]!=='string')throw new ApiError(502,'',[],'','',path,'POST');
        this.record={...body,...record};this.created.set(true);
      }catch(error){
        // No idempotency key exists: an unknown create result must never be replayed blindly.
        if(!(error instanceof ApiError)||error.status===0||error.status>=500)this.uncertain.set(true);
        throw error;
      }
    }else{
      // Corrections after relationship failure target the known record, never another create POST.
      if(this.recordUncertain){
        const id=recordId(owner,this.record),record=await this.api.request<CatalogueRecord>(path+'/'+encodeURIComponent(id));
        if(recordId(owner,record)!==id||typeof record[display]!=='string')throw new ApiError(502);
        this.record=record;this.recordUncertain=false;
      }
      // Preserve changed-field PUT semantics, including explicit reversions after a partial save.
      const changes=Object.fromEntries(Object.entries(body).filter(([key,value])=>(!this.editing||!original||value!==original[key]||this.attemptedFields.has(key))&&this.record![key]!==value));
      if(Object.keys(changes).length){
        if(this.editing)this.editPending.set(true);
        for(const key of Object.keys(changes))this.attemptedFields.add(key);
        this.recordUncertain=true;
        const record=await this.api.request<CatalogueRecord>(path+'/'+encodeURIComponent(recordId(owner,this.record)),'PUT',changes,csrf);
        if(recordId(owner,record)!==recordId(owner,this.record))throw new ApiError(502);
        this.record={...this.record,...changes,...record};this.recordUncertain=false;
      }
    }
    const id=recordId(owner,this.record!);
    // With no selected/attempted links, retain ordinary creation as one request.
    if(!selected.length&&!this.attemptedRelatedIds.size&&!this.initialRelatedIds.size)return this.finish(selected);
    const existing=await this.relationships(id,owner),linked=new Set(existing.map(row=>row[selection.relatedKey] as string));
    for(const relation of existing){
      const related=relation[selection.relatedKey] as string;
      if((this.initialRelatedIds.has(related)||this.attemptedRelatedIds.has(related))&&!desired.has(related)){
        // Remove only deselected initial links or links attempted by this flow, never unseen concurrent links.
        if(this.editing)this.editPending.set(true);
        await this.api.request('/tag_category_relationships/'+encodeURIComponent(relation['id_tag_category_relationships'] as string),'DELETE',undefined,csrf);
        linked.delete(related);
      }
    }
    for(const related of selected){
      if(linked.has(related))continue;
      this.attemptedRelatedIds.add(related);
      if(this.editing)this.editPending.set(true);
      try{
        await this.api.request('/tag_category_relationships','POST',{[selection.ownerKey]:id,[selection.relatedKey]:related},csrf);
      }catch(error){
        // A concurrent/repeated pair may already exist. Read to confirm; never retry the POST automatically.
        if(!(error instanceof ApiError)||error.status!==409)throw error;
        if(!(await this.relationships(id,owner)).some(row=>row[selection.relatedKey]===related))throw error;
      }
      linked.add(related);
    }
    return this.finish(selected);
  }
}

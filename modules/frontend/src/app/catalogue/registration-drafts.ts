import { Injectable, computed, signal } from '@angular/core';
import { RegistrationResource } from './models';
import { EditorValues } from './resources';
import { AssociationReceipt } from './tag-category-registration';

export interface RegistrationDraft {
  values:EditorValues;categoryIds:string[];tagIds:string[];originalAssociationIds:string[];
  technicalVisible:boolean;dirty:boolean;errors:Record<string,string>;failure:unknown;notice:string;
  receipt:AssociationReceipt;
}

/** Section-local drafts, including receipts required for safe partial-save retries. */
@Injectable()
export class RegistrationDrafts {
  private readonly entries=signal(new Map<RegistrationResource,RegistrationDraft>());
  readonly hasChanges=computed(()=>[...this.entries().values()].some(draft=>draft.dirty));
  get(resource:RegistrationResource):RegistrationDraft|undefined{return this.entries().get(resource);}
  save(resource:RegistrationResource,draft:RegistrationDraft):void{this.entries.update(entries=>new Map(entries).set(resource,draft));}
  remove(resource:RegistrationResource):void{this.entries.update(entries=>{const next=new Map(entries);next.delete(resource);return next;});}
  clear():void{this.entries.set(new Map());}
}

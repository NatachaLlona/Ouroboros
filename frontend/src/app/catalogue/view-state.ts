import { Injectable, effect, inject, signal } from '@angular/core';
import { Session } from '../auth/session';
import { Resource } from './models';
import { contract } from './resources';

export interface SearchCriteria {name:string;filters:Record<string,string>;fields:string[];order:string;direction:string;}
export interface ListContext {criteria:SearchCriteria;page:number;scroll:number;}
export function defaultCriteria(resource:Resource):SearchCriteria{return {name:'',filters:{},fields:[],order:contract(resource).defaultOrder,direction:'asc'};}
export function copyCriteria(value:SearchCriteria):SearchCriteria{return {...value,filters:{...value.filters},fields:[...value.fields]};}

/** Bounded criteria/context memory, scoped to the current authenticated session. */
@Injectable({providedIn:'root'})
export class CatalogueViewState {
  readonly lastResource=signal<Resource>('platforms');
  private readonly session=inject(Session);private scope='';
  private readonly contexts=new Map<Resource,ListContext>();
  private readonly searches=signal<Partial<Record<Resource,SearchCriteria[]>>>({});
  constructor(){effect(()=>{this.session.current();this.session.generation?.();this.sync();});}
  private key():string{const account=this.session.current();return account.authenticated?(account.username||'authenticated')+':'+(this.session.generation?.()??0):'';}
  private sync():void{
    const scope=this.key();
    if(scope!==this.scope){this.scope=scope;this.contexts.clear();this.searches.set({});this.lastResource.set('platforms');}
  }
  context(resource:Resource):ListContext|undefined{if(this.key()!==this.scope)return undefined;const value=this.contexts.get(resource);return value?{...value,criteria:copyCriteria(value.criteria)}:undefined;}
  remember(resource:Resource,value:ListContext):void{this.sync();if(this.scope){this.contexts.set(resource,{...value,criteria:copyCriteria(value.criteria)});this.lastResource.set(resource);}}
  recent(resource:Resource):SearchCriteria[]{if(this.key()!==this.scope)return [];return (this.searches()[resource]||[]).map(copyCriteria);}
  add(resource:Resource,value:SearchCriteria):void{
    this.sync();if(!this.scope)return;const item=copyCriteria(value),identity=JSON.stringify(item);
    const previous=this.searches()[resource]||[];
    this.searches.update(all=>({...all,[resource]:[item,...previous.filter(entry=>JSON.stringify(entry)!==identity)].slice(0,5)}));
  }
  clear(resource:Resource):void{this.sync();this.searches.update(all=>({...all,[resource]:[]}));}
}

import { Component, DestroyRef, Injector, afterNextRender, computed, effect, inject, signal, untracked } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { Session } from '../auth/session';
import { Api, ApiError, safeMessage } from '../shared/api';
import { CatalogueLayout } from '../shared/catalogue-layout';
import { ResourceTabs } from '../shared/resource-tabs';
import { Confirmation } from '../shared/confirmation';
import { Pagination } from '../shared/pagination';
import { Notice } from '../shared/notice';
import { Resource } from './models';
import { CatalogueFilters } from './filters';
import { CatalogueViewState, SearchCriteria, copyCriteria, defaultCriteria } from './view-state';
import { CataloguePage, CatalogueRecord, contract, filterLabel, isResource, recordId, resourceDefinitions, substringPattern } from './resources';

@Component({selector:'app-consultation',imports:[RouterLink,CatalogueLayout,ResourceTabs,Confirmation,Pagination,Notice,CatalogueFilters],template:`
  <app-catalogue-layout title="Consultar itens isolados" subtitle="Encontre, edite ou apague uma plataforma, tag ou Classificação da Obra." back="/consultar" backLabel="Voltar a Consultar" [wide]="true">
    <app-resource-tabs [selected]="selected()" [disabled]="deleting()" (selectedChange)="choose($event)" />
    @if(message()){<app-notice [text]="message()" [activation]="noticeVersion()" />}
    @if(!session.canCreate()){<p role="alert">{{session.current().authenticated?'Esta área requer permissões de catálogo: supervisor ou administrador.':'Entre para consultar o catálogo.'}}</p><button class="button" type="button" (click)="session.openLogin('Entre para consultar.','/consultas')">Entrar</button>}
    @else{
      <form class="search-form" (submit)="apply($event)"><fieldset [disabled]="deleting()">
        <app-catalogue-filters [resource]="selected()" [name]="name()" (nameChange)="name.set($event)" [filters]="filters()" (filtersChange)="filters.set($event)" [chosen]="chosenFields()" (chosenChange)="chosenFields.set($event)" [order]="order()" (orderChange)="order.set($event)" [direction]="direction()" (directionChange)="direction.set($event)" [open]="advanced()" (openChange)="advanced.set($event)" (applied)="apply()" (cleared)="clear()" />
      </fieldset></form>
      <section class="recent-searches" aria-label="Pesquisas recentes"><h2>Pesquisas recentes</h2>
        @if(recent().length){<ul>@for(search of recent();track $index){<li><button type="button" class="button recent-criteria" (click)="reapply(search)">{{recentLabel(search)}}</button></li>}</ul><button type="button" class="text-button" (click)="view.clear(selected())">Limpar histórico</button>}
        @else{<p class="help">As buscas aplicadas com sucesso aparecem aqui durante esta sessão.</p>}
      </section>
      @if(loading()){<p role="status">A consultar…</p>}
      @if(error()){<p class="form-error" role="alert">{{error()}}</p><button class="button" type="button" (click)="load(page())">Tentar novamente</button>}
      @else if(!loading()&&!items().length){<p role="status">Sem resultados para esta pesquisa.</p>}
      @if(items().length){<div class="table-scroll"><table><caption>{{definition().label}} — resultados</caption><thead><tr><th scope="col">Nome fantasia</th><th scope="col">Identificador</th>@if(selected()==='work_classifications'){<th scope="col">Posição (tier)</th>}<th scope="col">Ações</th></tr></thead><tbody>
        @for(item of items();track id(item)){<tr><td>{{item[definition().display]}}</td><td>{{id(item)}}</td>@if(selected()==='work_classifications'){<td>{{item['tier']}}</td>}<td><div class="row-actions"><a class="button" routerLink="/cadastros" [queryParams]="{resource:selected(),id:id(item)}" (click)="rememberEdit()" [attr.aria-label]="'Editar '+item[definition().display]">✎ <span>Editar</span></a><button class="button" type="button" [disabled]="loading()||deleting()" (click)="confirmDelete(item)" [attr.aria-label]="'Apagar '+item[definition().display]"><svg aria-hidden="true" viewBox="0 0 24 24" width="20" height="20"><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13M10 10v7M14 10v7" fill="none" stroke="currentColor" stroke-width="1.8"/></svg></button></div></td></tr>}
      </tbody></table></div>}
      <app-pagination [page]="page()" [count]="count()" [busy]="loading()||deleting()" (changed)="load($event)" />
    }
  </app-catalogue-layout>
  @if(pendingDelete();as item){<app-confirmation title="Tem certeza de que deseja apagar este item?" [name]="item[definition().display]+''" action="Apagar" [busy]="deleting()" [error]="deleteError()" (cancelled)="pendingDelete.set(null)" (confirmed)="remove()" />}
`})
export class Consultation {
  readonly session=inject(Session);private readonly api=inject(Api);private readonly route=inject(ActivatedRoute);private readonly injector=inject(Injector);
  readonly view=inject(CatalogueViewState);
  readonly selected=signal<Resource>('platforms');readonly definition=computed(()=>resourceDefinitions[this.selected()]);readonly metadata=computed(()=>contract(this.selected()));
  readonly name=signal('');readonly advanced=signal(false);readonly filters=signal<Record<string,string>>({});readonly chosenFields=signal<string[]>([]);readonly order=signal<string>(contract('platforms').defaultOrder);readonly direction=signal('asc');
  readonly items=signal<CatalogueRecord[]>([]);readonly count=signal(0);readonly page=signal(1);readonly loading=signal(false);readonly error=signal('');readonly message=signal('');readonly noticeVersion=signal(0);
  readonly pendingDelete=signal<CatalogueRecord|null>(null);readonly deleting=signal(false);readonly deleteError=signal('');private generation=0;private applied:Record<string,string|number>={};
  private readonly ready=signal(false);private activeCriteria=defaultCriteria('platforms');private initialScroll=0;
  readonly recent=computed(()=>this.view.recent(this.selected()));
  constructor(){inject(DestroyRef).onDestroy(()=>this.generation++);effect(()=>{if(this.ready()&&this.session.canCreate())untracked(()=>{const scroll=this.initialScroll;this.initialScroll=0;void this.load(this.page(),false,scroll);});});void this.initialize();}
  private async initialize():Promise<void>{
    try{const state=await this.session.ensure();const resource=this.route.snapshot.queryParamMap.get('resource');this.selected.set(isResource(resource)?resource:this.view.lastResource());
      const context=this.view.context(this.selected());this.restore(context?.criteria||defaultCriteria(this.selected()));this.page.set(context?.page||1);this.initialScroll=context?.scroll||0;
      if(!state.authenticated)this.session.openLogin('Entre para consultar.','/consultas');
    }catch(error){this.error.set(safeMessage(error));}finally{this.ready.set(true);}
  }
  label(key:string):string{return filterLabel(key,this.definition());}
  id(item:CatalogueRecord):string{return recordId(this.selected(),item);}
  private criteria():SearchCriteria{
    const supported=new Set<string>(this.metadata().filters.map(field=>field.key));const fields=this.chosenFields().filter(key=>supported.has(key));
    return {name:this.name(),fields,filters:Object.fromEntries(Object.entries(this.filters()).filter(([key])=>fields.includes(key))),order:this.order(),direction:this.direction()};
  }
  private query(criteria:SearchCriteria):Record<string,string|number>{
    const query:Record<string,string|number>=Object.fromEntries(Object.entries(criteria.filters).filter(([key,value])=>criteria.fields.includes(key)&&value!==''));
    if(!query[this.definition().display]&&criteria.name)query[this.definition().display]=substringPattern(criteria.name);
    return {...query,order_by:criteria.order,order_direction:criteria.direction};
  }
  private restore(criteria:SearchCriteria):void{const value=copyCriteria(criteria);this.name.set(value.name);this.filters.set(value.filters);this.chosenFields.set(value.fields);this.order.set(value.order);this.direction.set(value.direction);this.activeCriteria=value;this.applied=this.query(value);}
  setFilter(key:string,value:string):void{if(!this.metadata().filters.some(field=>field.key===key))return;if(!this.chosenFields().includes(key))this.chosenFields.update(fields=>[...fields,key]);this.filters.update(filters=>({...filters,[key]:value}));}
  choose(resource:Resource):void{if(this.deleting())return;this.generation++;this.selected.set(resource);this.items.set([]);this.count.set(0);this.page.set(1);this.restore(defaultCriteria(resource));this.message.set('');this.pendingDelete.set(null);void this.load(1);}
  clear():void{this.filters.set({});this.chosenFields.set([]);this.name.set('');this.apply();}
  apply(event?:Event):void{event?.preventDefault();if(this.deleting())return;this.advanced.set(false);this.activeCriteria=this.criteria();this.applied=this.query(this.activeCriteria);void this.load(1,true);}
  reapply(criteria:SearchCriteria):void{if(this.deleting())return;this.restore(criteria);this.apply();}
  recentLabel(criteria:SearchCriteria):string{const fields=Object.entries(criteria.filters).filter(([,value])=>value!=='').map(([key,value])=>this.label(key)+': '+value);return [criteria.name||'Todos os nomes',...fields,this.label(criteria.order)+' '+(criteria.direction==='asc'?'↑':'↓')].join(' · ');}
  rememberEdit():void{this.view.remember(this.selected(),{criteria:this.activeCriteria,page:this.page(),scroll:window.scrollY});}
  async load(page:number,recordSearch=false,scroll=0):Promise<void>{
    if(!this.session.canCreate())return;const generation=++this.generation,resource=this.selected(),epoch=this.session.generation?.()??0,criteria=copyCriteria(this.activeCriteria);this.loading.set(true);this.error.set('');this.items.set([]);
    try{const response=await this.api.request<CataloguePage>('/'+resource,'GET',undefined,undefined,{...this.applied,page,page_size:10});if(generation!==this.generation||epoch!==(this.session.generation?.()??0))return;
      const last=Math.max(1,Math.ceil(response.count/response.page_size));if(response.page>last){await this.load(last,recordSearch,scroll);return;}this.items.set(response.items);this.count.set(response.count);this.page.set(response.page);
      this.view.remember(resource,{criteria,page:response.page,scroll});if(recordSearch)this.view.add(resource,criteria);
      if(scroll>0)afterNextRender(()=>window.scrollTo({top:scroll,behavior:'auto'}),{injector:this.injector});
    }catch(error){if(generation===this.generation){this.error.set(safeMessage(error));if(error instanceof ApiError&&error.status===401){this.session.expire();this.session.openLogin('Entre para consultar.','/consultas');}}}
    finally{if(generation===this.generation)this.loading.set(false);}
  }
  confirmDelete(item:CatalogueRecord):void{this.deleteError.set('');this.pendingDelete.set(item);}
  async remove():Promise<void>{
    const item=this.pendingDelete();if(!item||this.deleting())return;this.deleting.set(true);this.deleteError.set('');
    try{await this.api.request('/'+this.selected()+'/'+this.id(item),'DELETE',undefined,this.session.current().csrf_token);this.pendingDelete.set(null);this.message.set('Item apagado.');this.noticeVersion.update(value=>value+1);await this.load(this.page());}
    catch(error){this.deleteError.set(safeMessage(error));if(error instanceof ApiError&&error.status===401){this.pendingDelete.set(null);this.session.expire();this.session.openLogin('Entre para consultar.','/consultas');}if(error instanceof ApiError&&error.code==='CSRF_REJECTED'){try{await this.session.ensure(true);}catch{/* Keep the original failure and require deliberate resubmission. */}}}
    finally{this.deleting.set(false);}
  }
}

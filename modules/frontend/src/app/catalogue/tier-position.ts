import { Component, DestroyRef, computed, effect, inject, input, model, output, signal, untracked } from '@angular/core';
import { Api, safeMessage } from '../shared/api';
import { FieldLabel } from '../shared/field-label';
import { CataloguePage, CatalogueRecord } from './resources';
import { SearchableDropdown, SelectOption } from '../shared/currency-select';
import { Pagination } from '../shared/pagination';

export const TIER_HELP_TEXT='💡 Inserting a classification at an occupied position shifts that classification and all following classifications down, preserving their order.';

/** Read bounded pages of the complete order; only the backend performs moves. */
@Component({selector:'app-tier-position',imports:[FieldLabel,SearchableDropdown,Pagination],template:`
  <div class="field"><app-field-label fieldId="tier" label="Position (tier)" [help]="help" />
    @if(loading()){<p role="status">Loading classification order…</p>}
    @if(failure()){<p class="field-error" role="alert">{{failure()}}</p><button class="button" type="button" (click)="load()">Refresh order</button>}
    <app-searchable-dropdown fieldId="tier" [choices]="positions()" [disabled]="loading()||!!failure()" [value]="value()" (valueChange)="value.set($event)" [error]="error()" describedBy="tier-help tier-error" searchLabel="Search position by number" searchPlaceholder="Search position" optionsLabel="Positions" emptyMessage="No positions found." />
    @if(!loading()&&!failure()){
      <p class="help">Complete current order ({{records().length}} classifications)</p>
      @if(records().length){<ol class="tier-order" [start]="(page()-1)*pageSize+1" aria-label="Current classification order">@for(item of visibleRecords();track item['id_work_classifications']){<li [value]="item['tier']">{{item['display_name_work_classifications']}}</li>}</ol><app-pagination [page]="page()" [size]="pageSize" [count]="records().length" (changed)="page.set($event)" />}
      @else{<p class="help">There are no classifications yet.</p>}
    }
    <p id="tier-error" class="field-error">{{error()}}</p>
  </div>
`})
export class TierPosition {
  readonly help=TIER_HELP_TEXT;readonly pageSize=10;readonly page=signal(1);
  readonly visibleRecords=computed(()=>this.records().slice((this.page()-1)*this.pageSize,this.page()*this.pageSize));
  readonly positions=computed<readonly SelectOption[]>(()=>[...(!this.editing()?[{value:'',label:'Insert at the last position ('+(this.records().length+1)+')'}]:[]),...this.records().map(item=>({value:String(item['tier']),label:String(item['tier'])}))]);
  readonly editing=input(false);readonly value=model('');readonly error=input('');readonly available=output<boolean>();
  readonly records=signal<CatalogueRecord[]>([]);readonly loading=signal(true);readonly failure=signal('');
  private readonly api=inject(Api);private generation=0;private destroyed=false;
  constructor(){effect(()=>{this.editing();untracked(()=>void this.load());});inject(DestroyRef).onDestroy(()=>{this.destroyed=true;this.generation++;});}
  select(event:Event):void{this.value.set((event.target as HTMLSelectElement).value);}
  async load():Promise<void>{
    const generation=++this.generation;this.loading.set(true);this.failure.set('');this.records.set([]);this.page.set(1);this.available.emit(false);
    try{
      const first=await this.api.request<CataloguePage>('/work_classifications','GET',undefined,undefined,{page:1,page_size:50,order_by:'tier',order_direction:'asc'},false);
      const records=[...first.items],count=first.count,pages=Math.ceil(count/50);
      for(let page=2;page<=pages;page++){
        if(generation!==this.generation||this.destroyed)return;
        const next=await this.api.request<CataloguePage>('/work_classifications','GET',undefined,undefined,{page,page_size:50,order_by:'tier',order_direction:'asc'},false);
        if(next.count!==count||next.page!==page)throw new Error('Classification order changed');
        records.push(...next.items);
      }
      if(generation!==this.generation||this.destroyed)return;
      records.sort((a,b)=>Number(a['tier'])-Number(b['tier']));
      if(records.length!==count||new Set(records.map(item=>item['id_work_classifications'])).size!==count||records.some((item,index)=>item['tier']!==index+1))throw new Error('Incomplete classification order');
      if(this.editing()&&!records.some(item=>String(item['tier'])===this.value()))throw new Error('Current classification position changed');
      this.records.set(records);this.available.emit(true);
    }catch(error){if(generation===this.generation&&!this.destroyed)this.failure.set(safeMessage(error)+' Could not verify the complete order. Refresh before saving.');}
    finally{if(generation===this.generation&&!this.destroyed)this.loading.set(false);}
  }
}

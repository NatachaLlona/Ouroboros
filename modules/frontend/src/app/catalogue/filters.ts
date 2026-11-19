import { Component, ElementRef, HostListener, computed, inject, input, model, output, viewChild } from '@angular/core';
import { ConsultationResource as Resource } from './models';
import { contract, filterLabel, consultationDefinitions as resourceDefinitions } from './resources';
import { FieldLabel, FANTASY_NAME_LABEL, FANTASY_NAME_HELP_TEXT } from '../shared/field-label';

/** Compact public filter picker; expanding its overlay never moves Search. */
@Component({selector:'app-catalogue-filters',imports:[FieldLabel],template:`
  <div class="consultation-filters">
    <div class="filter-primary">
      <div class="field"><app-field-label fieldId="name-search" [label]="nameLabel" [help]="nameHelp" /><input id="name-search" aria-describedby="name-search-help" [value]="name()" (input)="name.set(value($event))" placeholder="Search name" [disabled]="!!filters()[definition().display]"></div>
      <div class="filter-picker-wrap"><button #filterTrigger id="filter-trigger" class="button" type="button" [attr.aria-expanded]="open()" aria-controls="filter-options" (click)="open.set(!open())">Advanced filters <span aria-hidden="true">{{open()?'⌃':'⌄'}}</span></button>
        @if(open()){<div id="filter-options" class="filter-picker" (keydown.escape)="close()"><app-field-label fieldId="filter-trigger" label="Advanced filters" help="Choose filter fields. Match literal text at the start, middle or end. An advanced filter for the same name replaces this search. Pattern: % matches multiple characters, _ matches one. Use \\ to escape literal symbols." />@for(field of metadata().filters;track field.key){<label class="filter-choice"><input type="checkbox" [checked]="chosen().includes(field.key)" (change)="toggle(field.key)">{{label(field.key)}}</label>}</div>}
      </div>
      <div class="search-actions"><button class="button button-primary" type="submit">Search</button><button class="button" type="button" (click)="cleared.emit()">Clear filters</button></div>
      <div class="ordering-controls"><div class="field"><label for="order-by">Order by</label><select id="order-by" [value]="order()" (change)="order.set(value($event));applied.emit()">@for(key of metadata().orderBy;track key){<option [value]="key" [selected]="order()===key">{{label(key)}}</option>}</select></div><div class="field"><label for="order-direction">Direction</label><select id="order-direction" [value]="direction()" (change)="direction.set(value($event));applied.emit()"><option value="asc" [selected]="direction()==='asc'">Ascending</option><option value="desc" [selected]="direction()==='desc'">Descending</option></select></div></div>
    </div>
    <div class="selected-filter-values" aria-label="Selected filter values">
      @for(field of selectedDefinitions();track field.key){<div class="field selected-filter"><div class="filter-value-label"><app-field-label [fieldId]="'filter-'+field.key" [label]="label(field.key)" [help]="filterHelp(field.key,field.pattern)" /><button class="icon-button" type="button" [attr.aria-label]="'Remove filter '+label(field.key)" (click)="toggle(field.key)">×</button></div>
        @if(field.kind==='boolean'){<select [id]="'filter-'+field.key" [attr.aria-describedby]="filterHelp(field.key,field.pattern)?'filter-'+field.key+'-help':null" [value]="filters()[field.key]||''" (change)="set(field.key,value($event))"><option value="">Any</option><option value="true" [selected]="filters()[field.key]==='true'">Yes</option><option value="false" [selected]="filters()[field.key]==='false'">No</option></select>}
        @else if(field.choices.length){<select [id]="'filter-'+field.key" [attr.aria-describedby]="filterHelp(field.key,field.pattern)?'filter-'+field.key+'-help':null" [value]="filters()[field.key]||''" (change)="set(field.key,value($event))"><option value="">Any</option>@for(choice of field.choices;track choice){<option [value]="choice" [selected]="filters()[field.key]===choice">{{choice}}</option>}</select>}
        @else{<input [id]="'filter-'+field.key" [attr.aria-describedby]="filterHelp(field.key,field.pattern)?'filter-'+field.key+'-help':null" [type]="field.kind==='date'?'date':'text'" [attr.inputmode]="field.kind==='integer'?'numeric':field.kind==='decimal'?'decimal':null" [value]="filters()[field.key]||''" (input)="set(field.key,value($event))">}
      </div>}
    </div>
  </div>
`})
export class CatalogueFilters {
  readonly nameLabel=FANTASY_NAME_LABEL;readonly nameHelp=FANTASY_NAME_HELP_TEXT;
  filterHelp(key:string,pattern:boolean):string{if(key===this.definition().display)return FANTASY_NAME_HELP_TEXT;return [pattern?'Pattern: % matches multiple characters, _ matches one. Use \\ to escape literal symbols.':'',key.includes('created_at')||key==='filter_timezone'?'Day: YYYY-MM-DD; ranges also accept an ISO timestamp with an offset. End dates include the day; end timestamps are exclusive. Use an exact day or a range; the default IANA timezone is the application timezone.':''].filter(Boolean).join(' ');}
  private readonly host=inject(ElementRef<HTMLElement>);private readonly trigger=viewChild<ElementRef<HTMLButtonElement>>('filterTrigger');
  readonly resource=input.required<Resource>();readonly name=model('');readonly filters=model<Record<string,string>>({});readonly chosen=model<string[]>([]);readonly order=model('');readonly direction=model('asc');readonly open=model(false);
  readonly applied=output<void>();readonly cleared=output<void>();
  readonly definition=computed(()=>resourceDefinitions[this.resource()]);readonly metadata=computed(()=>contract(this.resource()));
  readonly selectedDefinitions=computed(()=>this.metadata().filters.filter(field=>this.chosen().includes(field.key)));
  label(key:string):string{return filterLabel(key,this.definition());}
  value(event:Event):string{return (event.target as HTMLInputElement).value;}
  close():void{this.open.set(false);this.trigger()?.nativeElement.focus();}
  @HostListener('document:click',['$event']) outside(event:MouseEvent):void{if(event.target instanceof Node&&!this.host.nativeElement.contains(event.target))this.open.set(false);}
  set(key:string,value:string):void{this.filters.update(filters=>({...filters,[key]:value}));}
  toggle(key:string):void{
    if(!this.metadata().filters.some(field=>field.key===key))return;
    if(this.chosen().includes(key)){this.chosen.update(fields=>fields.filter(field=>field!==key));this.filters.update(filters=>{const next={...filters};delete next[key];return next;});this.applied.emit();}
    else this.chosen.update(fields=>[...fields,key]);
  }
}

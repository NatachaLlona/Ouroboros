import { Component, DestroyRef, ElementRef, computed, effect, inject, input, model, output, signal, viewChild } from '@angular/core';
import { Api, safeMessage } from '../shared/api';
import { FieldLabel, FANTASY_NAME_LABEL, FANTASY_NAME_HELP_TEXT } from '../shared/field-label';
import { CataloguePage, CatalogueRecord, ResourceDefinition, recordId, substringPattern } from './resources';
@Component({selector:'app-name-autocomplete',imports:[FieldLabel],template:`
  <div class="field name-autocomplete" (focusout)="leave($event)">
    <app-field-label [fieldId]="definition().display" [label]="nameLabel" [help]="nameHelp" [required]="true" />
    <div class="completion-wrap"><input #nameInput [id]="definition().display" [value]="value()" (input)="typed($event)" (focus)="focused.set(true);open.set(true)" (blur)="completed.emit(false)" (keydown)="key($event)" role="combobox" aria-autocomplete="both" [attr.aria-expanded]="visible()" [attr.aria-controls]="visible()?listId():null" [attr.aria-activedescendant]="visible()&&active()>=0 ? listId()+'-'+active() : null" required aria-required="true" autocomplete="off" [attr.aria-describedby]="definition().display+'-help '+definition().display+'-error'">
    @if(focused() && suffix()){<span class="inline-completion" aria-hidden="true"><span class="completion-prefix">{{value()}}</span>{{suffix()}}</span>}
    @if(visible()){
      <div class="autocomplete-panel">
      <ul #list class="autocomplete-list" [id]="listId()" role="listbox" aria-label="Nomes fantasia existentes">
        @for(item of items();track id(item);let index=$index){<li [id]="listId()+'-'+index" role="option" [attr.aria-selected]="active()===index"><button tabindex="-1" type="button" [class.active]="active()===index" (mousedown)="$event.preventDefault()" (click)="accept(item)">{{item[definition().display]}}</button></li>}
      </ul>
      @if(items().length===limit){<p class="help autocomplete-guidance">Continue digitando para refinar a busca</p>}
      </div>
    }</div>
    <p class="field-error" [id]="definition().display+'-error'">{{error()}}</p>
    @if(loading()){<p class="help" role="status">A pesquisar…</p>}
    @if(searchError()){<p class="help" role="alert">{{searchError()}} <button class="text-button" type="button" (click)="search()">Tentar novamente</button></p>}
  </div>
`})
export class NameAutocomplete {
  readonly nameLabel=FANTASY_NAME_LABEL;readonly nameHelp=FANTASY_NAME_HELP_TEXT;
  readonly limit=20;
  readonly definition=input.required<ResourceDefinition>();readonly value=model('');readonly error=input('');readonly enabled=input(true);
  readonly selected=output<CatalogueRecord>();readonly completed=output<boolean>();readonly changed=output<void>();
  private readonly api=inject(Api);private readonly host=inject(ElementRef<HTMLElement>);private readonly list=viewChild<ElementRef<HTMLElement>>('list');
  readonly focused=signal(false);readonly open=signal(false);readonly loading=signal(false);readonly searchError=signal('');readonly items=signal<CatalogueRecord[]>([]);readonly count=signal(0);readonly active=signal(-1);
  readonly listId=computed(()=>this.definition().resource+'-name-options');
  readonly visible=computed(()=>this.enabled()&&this.open()&&!this.loading()&&!this.searchError()&&this.items().length>0);
  readonly suffix=computed(()=>{const text=this.value(),items=this.items();if(!text||this.count()!==1||items.length!==1)return '';const name=String(items[0][this.definition().display]);return name.toLocaleLowerCase('pt').startsWith(text.toLocaleLowerCase('pt'))?name.slice(text.length):'';});
  private timer?:ReturnType<typeof setTimeout>;private generation=0;
  constructor(){effect(()=>{this.definition();this.enabled();clearTimeout(this.timer);this.generation++;this.items.set([]);this.count.set(0);this.active.set(-1);this.open.set(false);this.loading.set(false);this.searchError.set('');});inject(DestroyRef).onDestroy(()=>{clearTimeout(this.timer);this.generation++;});}
  id(item:CatalogueRecord):string{return recordId(this.definition().resource,item);}
  typed(event:Event):void{this.value.set((event.target as HTMLInputElement).value);this.changed.emit();this.open.set(true);this.active.set(-1);clearTimeout(this.timer);this.generation++;this.items.set([]);this.count.set(0);this.searchError.set('');this.loading.set(false);if(this.value().trim()&&this.enabled())this.timer=setTimeout(()=>void this.search(),250);}
  async search():Promise<void>{
    const text=this.value();if(!text.trim()||!this.enabled())return;
    const generation=++this.generation,definition=this.definition();this.loading.set(true);this.searchError.set('');this.active.set(-1);
    try{const response=await this.api.request<CataloguePage>('/'+definition.resource,'GET',undefined,undefined,{[definition.display]:substringPattern(text),page:1,page_size:this.limit,order_by:definition.display,order_direction:'asc'});if(generation!==this.generation)return;this.items.set(response.items.slice(0,this.limit));this.count.set(response.count);}
    catch(error){if(generation===this.generation)this.searchError.set(safeMessage(error));}
    finally{if(generation===this.generation)this.loading.set(false);}
  }
  accept(item:CatalogueRecord):void{this.open.set(false);this.active.set(-1);this.selected.emit(item);}
  key(event:KeyboardEvent):void{
    if(event.key==='Escape'){this.open.set(false);this.active.set(-1);return;}
    if(event.key==='ArrowDown'||event.key==='ArrowUp'){event.preventDefault();this.open.set(true);const length=this.items().length;if(length){this.active.set(this.active()<0?(event.key==='ArrowDown'?0:length-1):(this.active()+(event.key==='ArrowDown'?1:-1)+length)%length);const item=this.list()?.nativeElement.children[this.active()];item?.scrollIntoView({block:'nearest'});}return;}
    if(event.key==='Enter'){event.preventDefault();if(this.open()&&this.active()>=0){this.accept(this.items()[this.active()]);return;}if(this.open()&&this.suffix()){this.accept(this.items()[0]);return;}this.open.set(false);this.completed.emit(true);return;}
    if(event.key==='Tab'&&!event.shiftKey&&this.value().trim()&&this.definition().technical){event.preventDefault();this.open.set(false);this.completed.emit(true);}
  }
  leave(event:FocusEvent):void{if(event.relatedTarget instanceof Node&&this.host.nativeElement.contains(event.relatedTarget))return;this.focused.set(false);this.open.set(false);}
}

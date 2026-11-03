import { Component, DestroyRef, computed, effect, inject, input, model, output, signal, untracked } from '@angular/core';
import { Api, ApiError, safeMessage } from '../shared/api';
import { FieldLabel } from '../shared/field-label';
import { MultiSelect } from '../shared/multi-select';
import { SelectOption } from '../shared/select-options';
import { readCataloguePages } from '../shared/catalogue-pages';
import { registrationDefinitions } from './resources';
import { TagCategoryOwner, tagCategoryAssociations } from './tag-category-association';

@Component({selector:'app-tag-category-field',imports:[FieldLabel,MultiSelect],template:`
  <div class="field"><app-field-label [fieldId]="selection().prefix+'-selection'" [label]="selection().label" />
    <app-multi-select [fieldId]="selection().prefix+'-selection'" [label]="selection().label" [placeholder]="selection().placeholder" [selectedCountLabel]="selection().selectedCountLabel" [emptyMessage]="selection().emptyMessage" [noResultsMessage]="selection().noResultsMessage" [choices]="allChoices()" [addLabel]="createLabel()" (addRequested)="createRequested.emit()" [value]="value()" (valueChange)="value.set($event)" [error]="error()" [disabled]="disabled()||loading()||!!failure()" [describedBy]="selection().prefix+'-status '+selection().prefix+'-error'" />
    <p [id]="selection().prefix+'-error'" class="field-error">{{error()}}</p>
    <div [id]="selection().prefix+'-status'">@if(loading()){<p class="help" role="status">{{selection().loadingMessage}}</p>}
    @if(failure()){<p class="field-error" role="alert">{{failure()}}</p><button type="button" class="text-button" [disabled]="disabled()||loading()" (click)="load()">Tentar novamente</button>}</div>
  </div>
`})
export class TagCategoryField {
  readonly allowCreate=input(false);readonly createRequested=output<void>();readonly extraChoices=input<readonly SelectOption[]>([]);readonly refresh=input(0);
  readonly createLabel=computed(()=>!this.allowCreate()?'':this.owner()==='tags'?'Adicionar nova categoria de tag':'Adicionar nova tag');
  readonly allChoices=computed(()=>[...this.extraChoices(),...this.choices()]);
  readonly owner=input<TagCategoryOwner>('tags');readonly selection=computed(()=>tagCategoryAssociations[this.owner()]);
  readonly value=model<string[]>([]);readonly disabled=input(false);readonly error=input('');readonly choices=signal<SelectOption[]>([]);readonly loading=signal(false);readonly failure=signal('');
  private readonly api=inject(Api);private generation=0;private destroyed=false;
  constructor(){inject(DestroyRef).onDestroy(()=>{this.destroyed=true;this.generation++;});effect(()=>{this.owner();this.refresh();untracked(()=>void this.load());});}
  async load():Promise<void>{
    const generation=++this.generation,current=()=>!this.destroyed&&generation===this.generation,selection=this.selection(),display=registrationDefinitions[selection.related].display;this.loading.set(true);this.failure.set('');
    try{const rows=await readCataloguePages(this.api,'/'+selection.related,selection.relatedKey,{order_by:display,order_direction:'asc'},current);if(!current())return;
      const choices=rows.map(row=>{const name=row[display];if(typeof name!=='string')throw new ApiError(502);return {value:row[selection.relatedKey] as string,label:name.trim()?name:selection.unnamedLabel};});this.choices.set(choices);
    }catch(error){if(current())this.failure.set(safeMessage(error));}finally{if(current())this.loading.set(false);}
  }
}

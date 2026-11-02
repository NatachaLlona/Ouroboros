import { Component, DestroyRef, inject, input, model, signal } from '@angular/core';
import { Api, ApiError, safeMessage } from '../shared/api';
import { FieldLabel } from '../shared/field-label';
import { MultiSelect } from '../shared/multi-select';
import { SelectOption } from '../shared/select-options';
import { readCataloguePages } from '../shared/catalogue-pages';

@Component({selector:'app-tag-category-field',imports:[FieldLabel,MultiSelect],template:`
  <div class="field"><app-field-label fieldId="tag-category-selection" label="Categorias de Tag" />
    <app-multi-select fieldId="tag-category-selection" label="Categorias de Tag" placeholder="Selecione categorias" selectedCountLabel="categorias selecionadas" emptyMessage="Nenhuma categoria cadastrada." noResultsMessage="Nenhuma categoria encontrada." [choices]="choices()" [value]="value()" (valueChange)="value.set($event)" [error]="error()" [disabled]="disabled()||loading()||!!failure()" describedBy="tag-category-status tag-category-error" />
    <p id="tag-category-error" class="field-error">{{error()}}</p>
    <div id="tag-category-status">@if(loading()){<p class="help" role="status">A carregar categorias…</p>}
    @if(failure()){<p class="field-error" role="alert">{{failure()}}</p><button type="button" class="text-button" [disabled]="disabled()||loading()" (click)="load()">Tentar novamente</button>}</div>
  </div>
`})
export class TagCategoryField {
  readonly value=model<string[]>([]);readonly disabled=input(false);readonly error=input('');readonly choices=signal<SelectOption[]>([]);readonly loading=signal(false);readonly failure=signal('');
  private readonly api=inject(Api);private generation=0;private destroyed=false;
  constructor(){inject(DestroyRef).onDestroy(()=>{this.destroyed=true;this.generation++;});void this.load();}
  async load():Promise<void>{
    const generation=++this.generation,current=()=>!this.destroyed&&generation===this.generation;this.loading.set(true);this.failure.set('');
    try{const rows=await readCataloguePages(this.api,'/tag_categories','id_tag_categories',{order_by:'display_name_tag_categories',order_direction:'asc'},current);if(!current())return;
      const choices=rows.map(row=>{const name=row['display_name_tag_categories'];if(typeof name!=='string')throw new ApiError(502);return {value:row['id_tag_categories'] as string,label:name.trim()?name:'Categoria sem nome'};});this.choices.set(choices);
    }catch(error){if(current())this.failure.set(safeMessage(error));}finally{if(current())this.loading.set(false);}
  }
}

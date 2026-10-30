import { Component, computed, input, model } from '@angular/core';
import { form, FormField, required, maxLength } from '@angular/forms/signals';
import { FieldDefinition } from '../catalogue/resources';
import { MoneyInput } from './money-input';
import { CurrencySelect } from './currency-select';
import { FieldLabel } from './field-label';
import { DescriptionInput } from './description-input';
import { currencies, priceError } from './money';
@Component({selector:'app-form-field',imports:[FormField,MoneyInput,CurrencySelect,FieldLabel,DescriptionInput],template:`
  <div class="field">@if(definition().kind!=='boolean'){<app-field-label [fieldId]="definition().key" [label]="definition().label" [required]="isRequired()" [help]="helpText()" />}
  @switch(definition().kind){
    @case('textarea'){@if(definition().key.startsWith('description_')){<app-description-input [fieldId]="definition().key" [value]="value()" (valueChange)="value.set($event)" [error]="error()" />}@else{<textarea [id]="definition().key" [formField]="field" [attr.aria-describedby]="descriptionId()" [attr.aria-invalid]="error() ? 'true' : null"></textarea>}}
    @case('boolean'){<label class="check" [for]="definition().key"><input type="checkbox" [id]="definition().key" [checked]="value()==='true'" (change)="toggle($event)">{{definition().label}}</label>}
    @case('decimal'){<app-money-input [showPrecision]="false" [fieldId]="definition().key" [value]="value()" (valueChange)="value.set($event)" [error]="error()" />}
    @case('currency'){<app-currency-select [fieldId]="definition().key" [required]="isRequired()" [value]="value()" (valueChange)="value.set($event)" [error]="error()" />}
    @case('access'){<select [id]="definition().key" [value]="legacyAccess()?'':value()" (change)="select($event)" [attr.aria-required]="definition().required" [attr.aria-describedby]="descriptionId()"><option value="" [selected]="value()===''||legacyAccess()" [disabled]="legacyAccess()">Selecione uma opção</option>
      <option value="application" [selected]="value()==='application'">Aplicativo</option><option value="website" [selected]="value()==='website'">Site</option></select>}
    @default{<input [id]="definition().key" [type]="definition().kind==='url' ? 'url' : 'text'" [attr.inputmode]="definition().kind==='decimal' ? 'decimal' : definition().kind==='integer' ? 'numeric' : null" [formField]="field" [attr.aria-describedby]="descriptionId()" [attr.aria-invalid]="error() ? 'true' : null">}
  }
  <p class="field-error" [id]="definition().key+'-error'">{{message()}}</p></div>
`})
export class SharedFormField {
  readonly definition=input<FieldDefinition>({key:'field',label:'Campo',kind:'text'});readonly value=model('');readonly error=input('');
  readonly requiredOverride=input(false);readonly isRequired=computed(()=>this.requiredOverride()||this.definition().required===true);
  readonly field=form(this.value,path=>{required(path,{when:()=>this.definition().required===true});maxLength(path,2083,{when:()=>this.definition().kind==='url'});});
  readonly helpText=computed(()=>[this.definition().help,this.definition().kind==='access'&&this.legacyAccess()?'Tipos atuais: '+this.value()+'. Não serão alterados ao guardar outros campos. Escolher Aplicativo ou Site substitui a lista completa.':''].filter(Boolean).join(' '));
  readonly descriptionId=computed(()=>(this.helpText()?this.definition().key+'-help ':'')+this.definition().key+'-error');
  readonly currencies=currencies;
  readonly currency=computed(()=>currencies.find(item=>item.code===this.value()));
  readonly knownCurrency=computed(()=>!!this.currency());
  readonly legacyAccess=computed(()=>!!this.value()&&!['application','website'].includes(this.value()));
  readonly message=computed(()=>this.error()||(this.definition().kind==='decimal'?priceError(this.value()):''));
  select(event:Event):void{this.value.set((event.target as HTMLSelectElement).value);}
  toggle(event:Event):void{this.value.set(String((event.target as HTMLInputElement).checked));}
}

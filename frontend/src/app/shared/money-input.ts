import { Component, computed, input, model, signal } from '@angular/core';
import { priceDisplay, priceError, priceValue } from './money';

/** Formatting runs on blur only; focusing restores the exact editable decimal. */
@Component({selector:'app-money-input',template:`
  <input [id]="fieldId()" type="text" inputmode="decimal" placeholder="00,00" [value]="display()" (input)="typed($event)" (focus)="focused.set(true)" (blur)="focused.set(false)" [attr.aria-describedby]="fieldId()+'-help '+fieldId()+'-error'+(exactNote()?' '+fieldId()+'-precision':'')" [attr.aria-invalid]="invalid()?'true':null">
  @if(showPrecision()&&exactNote()){<p class="help" [id]="fieldId()+'-precision'">Apresentação arredondada a duas casas. Valor exato enviado: {{canonical()}}. Ao focar pode editar todas as casas.</p>}
`})
export class MoneyInput {
  readonly showPrecision=input(true);
  readonly fieldId=input.required<string>();readonly value=model('');readonly error=input('');readonly focused=signal(false);
  readonly invalid=computed(()=>this.error()||priceError(this.value()));
  readonly display=computed(()=>this.focused()||this.invalid()?this.value():priceDisplay(this.value()));
  readonly canonical=computed(()=>this.invalid()?'':priceValue(this.value())||'');
  readonly exactNote=computed(()=>this.showPrecision()&&!this.invalid()&&!!this.value()&&this.canonical()!==this.display().replace(',','.'));
  typed(event:Event):void{this.value.set((event.target as HTMLInputElement).value);}
}

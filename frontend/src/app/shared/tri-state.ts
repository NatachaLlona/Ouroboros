import { Component, input, model } from '@angular/core';

/** A native checkbox with explicit false and a separate unanswered reset. */
@Component({selector:'app-tri-state',template:`
  <div class="tri-state-control"><input [id]="fieldId()" type="checkbox" [checked]="value()==='true'" [indeterminate]="value()===''" [attr.aria-checked]="value()===''?'mixed':value()" [attr.aria-required]="required()?'true':null" [attr.aria-describedby]="fieldId()+'-state '+fieldId()+'-help '+fieldId()+'-error'" [attr.aria-invalid]="error()?'true':null" (change)="toggle()">
  <span [id]="fieldId()+'-state'">{{value()===''?'Por responder':value()==='true'?'Sim':'Não'}}</span>
  <button class="text-button" type="button" [disabled]="value()===''" [attr.aria-label]="'Limpar resposta: '+label()" (click)="value.set('')">Limpar resposta</button></div>
`})
export class TriState {
  readonly fieldId=input.required<string>();readonly label=input.required<string>();readonly required=input(false);readonly error=input('');readonly value=model('');
  toggle():void{this.value.set(this.value()==='true'?'false':'true');}
}

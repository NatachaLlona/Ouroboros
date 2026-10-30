import { Component, ElementRef, afterNextRender, input, output, viewChild } from '@angular/core';
@Component({selector:'app-confirmation',template:`<dialog #dialog class="modal" aria-labelledby="confirmation-title" (cancel)="cancel($event)"><div class="modal-content"><h2 id="confirmation-title">{{title()}}</h2><p>{{name()}}</p>@if(error()){<p class="form-error" role="alert">{{error()}}</p>}<div class="dialog-actions"><button #cancelButton class="button button-primary" type="button" [disabled]="busy()" (click)="cancelled.emit()">{{cancelLabel()}}</button><button class="button confirmation-affirmative" type="button" [disabled]="busy()" (click)="confirmed.emit()">{{busy() ? 'A processar…' : action()}}</button></div></div></dialog>`})
export class Confirmation {
  readonly title=input.required<string>();readonly name=input('');readonly action=input('Confirmar');readonly busy=input(false);readonly error=input('');readonly confirmed=output<void>();readonly cancelled=output<void>();
  readonly cancelLabel=input('Cancelar');
  private readonly cancelButton=viewChild.required<ElementRef<HTMLButtonElement>>('cancelButton');
  private readonly dialog=viewChild.required<ElementRef<HTMLDialogElement>>('dialog');private readonly previous=document.activeElement as HTMLElement|null;
  constructor(){afterNextRender(()=>{this.dialog().nativeElement.showModal();this.cancelButton().nativeElement.focus();});}
  cancel(event:Event):void{event.preventDefault();if(!this.busy())this.cancelled.emit();}
  ngOnDestroy():void{this.previous?.focus();}
}

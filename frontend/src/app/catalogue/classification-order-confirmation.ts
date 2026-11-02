import { Component, ElementRef, afterNextRender, input, output, viewChild } from '@angular/core';

@Component({selector:'app-classification-order-confirmation',template:`
  <dialog #dialog class="modal" aria-labelledby="order-confirmation-title" aria-describedby="order-confirmation-message" (cancel)="dismiss($event)" (close)="dismissed.emit()">
    <div class="modal-content">
      <div class="modal-top"><h2 id="order-confirmation-title">🔄 Confirmar alteração da ordem</h2><button class="icon-button" type="button" aria-label="Fechar confirmação" (click)="dismissed.emit()">×</button></div>
      <div id="order-confirmation-message"><p>Você está prestes a inserir esta classificação na posição <strong>{{position()}}</strong>.</p><p><strong>A classificação que ocupava essa posição e as seguintes serão deslocadas automaticamente.</strong></p><p>Como deseja continuar?</p></div>
      <div class="dialog-actions">
        <button #returnButton class="button button-primary" type="button" (click)="dismissed.emit()">🔙 Retornar ao formulário</button>
        <button class="button confirmation-affirmative" type="button" (click)="appended.emit()">⬇️ Inserir na última posição</button>
        <button class="button confirmation-affirmative" type="button" (click)="confirmed.emit()">✅ Confirmar inserção</button>
      </div>
    </div>
  </dialog>
`})
export class ClassificationOrderConfirmation {
  readonly position=input.required<string>();readonly appended=output<void>();readonly confirmed=output<void>();readonly dismissed=output<void>();
  private readonly dialog=viewChild.required<ElementRef<HTMLDialogElement>>('dialog');
  private readonly returnButton=viewChild.required<ElementRef<HTMLButtonElement>>('returnButton');
  private readonly previous=document.activeElement as HTMLElement|null;
  constructor(){afterNextRender(()=>{this.dialog().nativeElement.showModal();this.returnButton().nativeElement.focus();});}
  dismiss(event:Event):void{event.preventDefault();this.dismissed.emit();}
  ngOnDestroy():void{this.previous?.focus();}
}

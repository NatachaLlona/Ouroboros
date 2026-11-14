import { Component, ElementRef, afterNextRender, input, output, viewChild } from '@angular/core';

@Component({selector:'app-classification-order-confirmation',template:`
  <dialog #dialog class="modal" aria-labelledby="order-confirmation-title" aria-describedby="order-confirmation-message" (cancel)="dismiss($event)" (close)="dismissed.emit()">
    <div class="modal-content">
      <div class="modal-top"><h2 id="order-confirmation-title">🔄 Confirm order change</h2><button class="icon-button" type="button" aria-label="Close confirmation" (click)="dismissed.emit()">×</button></div>
      <div id="order-confirmation-message"><p>You are about to insert this classification at position <strong>{{position()}}</strong>.</p><p><strong>The classification at this position and all following classifications will shift automatically.</strong></p><p>How would you like to continue?</p></div>
      <div class="dialog-actions">
        <button #returnButton class="button button-primary" type="button" (click)="dismissed.emit()">🔙 Return to form</button>
        <button class="button confirmation-affirmative" type="button" (click)="appended.emit()">⬇️ Insert at the last position</button>
        <button class="button confirmation-affirmative" type="button" (click)="confirmed.emit()">✅ Confirm insertion</button>
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

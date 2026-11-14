import { Component, ElementRef, afterNextRender, input, output, viewChild } from '@angular/core';

@Component({selector:'app-classification-name-confirmation',template:`
  <dialog #dialog class="modal" aria-labelledby="technical-confirmation-title" aria-describedby="technical-confirmation-message" (cancel)="dismiss($event)" (close)="dismissed.emit()">
    <div class="modal-content">
      <div class="modal-top"><h2 id="technical-confirmation-title">Confirm Technical Name</h2><button class="icon-button" type="button" aria-label="Close confirmation" (click)="dismissed.emit()">×</button></div>
      <div id="technical-confirmation-message"><p>The technical name for this classification will be:</p><p><strong>{{name()}}</strong></p><p>Keep this name or change it?</p></div>
      <div class="dialog-actions"><button #modifyButton class="button button-primary" type="button" (click)="modified.emit()">Change</button><button class="button confirmation-affirmative" type="button" (click)="kept.emit()">Keep</button></div>
    </div>
  </dialog>
`})
export class ClassificationNameConfirmation {
  readonly name=input.required<string>();readonly kept=output<void>();readonly modified=output<void>();readonly dismissed=output<void>();
  private readonly dialog=viewChild.required<ElementRef<HTMLDialogElement>>('dialog');
  private readonly modifyButton=viewChild.required<ElementRef<HTMLButtonElement>>('modifyButton');
  private readonly previous=document.activeElement as HTMLElement|null;
  constructor(){afterNextRender(()=>{this.dialog().nativeElement.showModal();this.modifyButton().nativeElement.focus();});}
  dismiss(event:Event):void{event.preventDefault();this.dismissed.emit();}
  ngOnDestroy():void{this.previous?.focus();}
}

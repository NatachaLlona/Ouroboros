import { Component, computed, input, model, signal } from '@angular/core';
import { FormValueControl } from '@angular/forms/signals';
import { DESCRIPTION_MAX_LENGTH, descriptionLength } from './description';

/** Reject whole over-limit edits, never slice UTF-16 or interrupt IME composition. */
@Component({selector:'app-description-input',template:`
  <div class="description-control"><textarea [id]="fieldId()" [value]="value()" [disabled]="disabled()" [attr.aria-describedby]="fieldId()+'-counter '+fieldId()+'-error'+(notice()||overLimit()? ' '+fieldId()+'-limit-note':'')" [attr.aria-invalid]="error()||overLimit()?'true':null" (beforeinput)="beforeInput($event)" (paste)="paste($event)" (input)="typed($event)" (compositionstart)="startComposition($event)" (compositionend)="endComposition($event)"></textarea>
  <span class="description-counter" [id]="fieldId()+'-counter'">{{count()}} / {{maximum}}</span></div>
  @if(notice()||overLimit()){<p class="field-error" role="status" [id]="fieldId()+'-limit-note'">{{overLimit()?'Descrição existente acima do limite. O texto foi preservado; reduza-o para guardar alterações nesta descrição.':notice()}}</p>}
`})
export class DescriptionInput implements FormValueControl<string> {
  readonly fieldId=input.required<string>();readonly value=model('');readonly disabled=input(false);readonly error=input('');readonly maximum=DESCRIPTION_MAX_LENGTH;
  readonly notice=signal('');private readonly compositionDraft=signal<string|null>(null);private composing=false;
  readonly count=computed(()=>descriptionLength(this.compositionDraft()??this.value()));readonly overLimit=computed(()=>descriptionLength(this.value())>this.maximum);
  private selectionStart=0;private selectionEnd=0;
  private permitted(candidate:string):boolean{const size=descriptionLength(candidate),current=descriptionLength(this.value());return size<=this.maximum||(current>this.maximum&&size<current);}
  private snapshot(input:HTMLTextAreaElement):void{this.selectionStart=input.selectionStart;this.selectionEnd=input.selectionEnd;}
  private blocked():void{this.notice.set('Limite de '+this.maximum+' caracteres atingido.');}
  beforeInput(event:Event):void{
    const edit=event as InputEvent,input=event.target as HTMLTextAreaElement;
    if(this.composing||edit.isComposing)return;
    this.snapshot(input);if(!edit.inputType.startsWith('insert')||edit.data===null)return;
    const candidate=input.value.slice(0,input.selectionStart)+edit.data+input.value.slice(input.selectionEnd);
    if(!this.permitted(candidate)&&edit.cancelable){edit.preventDefault();this.blocked();}
  }
  paste(event:ClipboardEvent):void{
    if(this.composing)return;const input=event.target as HTMLTextAreaElement;this.snapshot(input);const text=event.clipboardData?.getData('text/plain');if(text===undefined)return;
    const candidate=input.value.slice(0,input.selectionStart)+text+input.value.slice(input.selectionEnd);
    if(!this.permitted(candidate)){event.preventDefault();this.blocked();}
  }
  private commit(input:HTMLTextAreaElement):void{
    if(this.permitted(input.value)){this.value.set(input.value);this.notice.set('');}
    else{input.value=this.value();input.setSelectionRange(this.selectionStart,this.selectionEnd);this.blocked();}
    this.compositionDraft.set(null);
  }
  typed(event:Event):void{const input=event.target as HTMLTextAreaElement;if(this.composing||(event as InputEvent).isComposing){this.compositionDraft.set(input.value);return;}this.commit(input);}
  startComposition(event:Event):void{this.composing=true;this.snapshot(event.target as HTMLTextAreaElement);}
  endComposition(event:Event):void{this.composing=false;this.commit(event.target as HTMLTextAreaElement);}
}

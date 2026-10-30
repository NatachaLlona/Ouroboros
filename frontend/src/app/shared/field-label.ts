import { Component, ElementRef, HostListener, inject, input, signal } from '@angular/core';

export const FANTASY_NAME_LABEL='Nome Fantasia';
export const FANTASY_NAME_HELP_TEXT='✨ Aqui você pode soltar a criatividade! Personalize com emojis, símbolos e pontuação, tudo do seu jeitinho. 💜';
export const PRICE_HELP_TEXT='💰 Informe o valor desejado. Use vírgula para separar os centavos (ex.: 10,50).';

/** One presentation for labels, required markers and accessible contextual help. */
@Component({selector:'app-field-label',template:`
  <div class="label-row" (mouseenter)="help()&&open.set(true)" (mouseleave)="leaveHover()" (focusout)="leaveFocus($event)">
    <label [id]="fieldId()+'-label'" [for]="fieldId()">@if(required()){<strong class="required-star" aria-hidden="true">*</strong>{{' '}}}{{label()}}</label>
    @if(help()){
      <button type="button" class="help-button" [attr.aria-label]="'Ajuda sobre '+label()" [attr.aria-expanded]="open()" [attr.aria-controls]="fieldId()+'-help'" [attr.aria-describedby]="fieldId()+'-help'" (focus)="open.set(true)" (click)="open.set(true)"><span aria-hidden="true">ⓘ</span></button>
      <span class="field-tooltip" role="tooltip" [id]="fieldId()+'-help'" [hidden]="!open()">{{help()}}</span>
    }
  </div>
`})
export class FieldLabel {
  readonly fieldId=input.required<string>();readonly label=input.required<string>();readonly required=input(false);readonly help=input('');readonly open=signal(false);
  private readonly host=inject(ElementRef<HTMLElement>);
  leaveHover():void{if(!this.host.nativeElement.contains(document.activeElement))this.open.set(false);}
  leaveFocus(event:FocusEvent):void{if(!this.host.nativeElement.contains(event.relatedTarget as Node|null))this.open.set(false);}
  @HostListener('document:click',['$event']) outside(event:MouseEvent):void{if(event.target instanceof Node&&!this.host.nativeElement.contains(event.target))this.open.set(false);}
  @HostListener('keydown.escape',['$event'])
  @HostListener('document:keydown.escape',['$event']) escape(event:Event):void{if(this.open()){this.open.set(false);event.preventDefault();event.stopPropagation();}}
}

import { Component, ElementRef, HostListener, Injector, afterNextRender, computed, effect, inject, input, model, signal, viewChild } from '@angular/core';
import { currencies } from './money';
export interface SelectOption {value:string;label:string;}

@Component({selector:'app-currency-select, app-searchable-dropdown',host:{class:'searchable-dropdown'},template:`
  <div (focusout)="leave($event)">
    <button #trigger [id]="fieldId()" type="button" class="currency-trigger" role="combobox" aria-haspopup="listbox" [disabled]="disabled()" [attr.aria-expanded]="open()" [attr.aria-controls]="open()?fieldId()+'-options':null" [attr.aria-required]="required()" [attr.aria-invalid]="!!error()" [attr.aria-describedby]="describedBy()||fieldId()+'-error'" (click)="toggle()" (keydown.arrowdown)="$event.preventDefault();show()" (keydown.escape)="close($event)">{{selected()?.label||placeholder()}} <span aria-hidden="true">⌄</span></button>
    @if(open()){
      <div class="currency-menu"><input #search type="search" [attr.aria-label]="searchLabel()" [placeholder]="searchPlaceholder()" [value]="query()" (input)="filter($event)" (keydown)="key($event)" role="combobox" aria-autocomplete="list" aria-expanded="true" [attr.aria-controls]="fieldId()+'-options'" [attr.aria-activedescendant]="active()>=0?fieldId()+'-option-'+active():null">
      <ul #options [id]="fieldId()+'-options'" role="listbox" [attr.aria-label]="optionsLabel()">@for(choice of matches();track choice.value;let index=$index){<li role="option" [id]="fieldId()+'-option-'+index" [class.active]="index===active()" [attr.aria-selected]="value()===choice.value" (mousedown)="$event.preventDefault()" (click)="choose(choice.value)">{{choice.label}}</li>}</ul>
      @if(!matches().length){<p role="status">{{emptyMessage()}}</p>}
      </div>
    }
  </div>
`})
export class SearchableDropdown {
  readonly choices=input<readonly SelectOption[]>(currencies.map(choice=>({value:choice.code,label:choice.code+' — '+choice.name})));
  readonly placeholder=input('Selecione uma opção');readonly searchLabel=input('Pesquisar moeda por código ou nome');readonly searchPlaceholder=input('Pesquisar moeda');readonly optionsLabel=input('Moedas');readonly emptyMessage=input('Nenhuma moeda encontrada.');readonly disabled=input(false);readonly describedBy=input('');
  readonly fieldId=input.required<string>();readonly required=input(false);readonly error=input('');readonly value=model('');
  readonly open=signal(false);readonly query=signal('');readonly active=signal(-1);
  readonly selected=computed(()=>this.choices().find(choice=>choice.value===this.value()));
  readonly matches=computed(()=>{const text=this.query().trim().toLocaleLowerCase('pt');return this.choices().filter(choice=>choice.label.toLocaleLowerCase('pt').includes(text));});
  private readonly injector=inject(Injector);private readonly host=inject(ElementRef<HTMLElement>);
  private readonly search=viewChild<ElementRef<HTMLInputElement>>('search');private readonly trigger=viewChild.required<ElementRef<HTMLButtonElement>>('trigger');
  private readonly options=viewChild<ElementRef<HTMLElement>>('options');
  constructor(){effect(()=>{if(this.disabled())this.open.set(false);});}
  show():void{if(this.disabled())return;this.query.set('');this.active.set(-1);this.open.set(true);afterNextRender(()=>this.search()?.nativeElement.focus(),{injector:this.injector});}
  toggle():void{if(this.open())this.open.set(false);else this.show();}
  filter(event:Event):void{this.query.set((event.target as HTMLInputElement).value);this.active.set(-1);}
  choose(code:string):void{this.value.set(code);this.open.set(false);this.trigger().nativeElement.focus();}
  leave(event:FocusEvent):void{if(!this.host.nativeElement.contains(event.relatedTarget as Node|null))this.open.set(false);}
  @HostListener('document:click',['$event']) outside(event:MouseEvent):void{if(event.target instanceof Node&&!this.host.nativeElement.contains(event.target))this.open.set(false);}
  close(event:Event):void{if(this.open()){event.preventDefault();event.stopPropagation();this.open.set(false);this.trigger().nativeElement.focus();}}
  key(event:KeyboardEvent):void{
    if(['ArrowDown','ArrowUp','Enter','Escape'].includes(event.key))event.preventDefault();
    if(event.key==='Escape'){event.stopPropagation();this.open.set(false);this.trigger().nativeElement.focus();}
    else if(event.key==='ArrowDown')this.active.set(Math.min(this.matches().length-1,this.active()+1));
    else if(event.key==='ArrowUp')this.active.set(this.matches().length?Math.max(0,this.active()<0?this.matches().length-1:this.active()-1):-1);
    else if(event.key==='Enter'){event.stopPropagation();const choice=this.matches()[this.active()];if(choice)this.choose(choice.value);}
    if(event.key==='ArrowDown'||event.key==='ArrowUp')this.options()?.nativeElement.children[this.active()]?.scrollIntoView?.({block:'nearest'});
  }
}
export { SearchableDropdown as CurrencySelect };

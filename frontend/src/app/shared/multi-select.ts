import { Component, ElementRef, HostListener, Injector, afterNextRender, computed, effect, inject, input, model, signal, viewChild } from '@angular/core';
import { SelectOption, filterSelectOptions, uniqueSelectValues } from './select-options';

/** Shared searchable checkbox dropdown; selection remains controlled by the form owner. */
@Component({selector:'app-multi-select',host:{class:'searchable-dropdown'},template:`
  <div (focusout)="leave($event)">
    <button #trigger [id]="fieldId()" type="button" class="currency-trigger" aria-haspopup="dialog" [attr.aria-expanded]="open()" [attr.aria-controls]="open()?fieldId()+'-panel':null" [attr.aria-describedby]="describedBy()||null" [attr.aria-invalid]="!!error()" [disabled]="disabled()" (click)="toggle()" (keydown.arrowdown)="$event.preventDefault();show()" (keydown.escape)="close($event)">{{summary()}} <span aria-hidden="true">⌄</span></button>
    @if(open()){
      <div class="currency-menu multi-select-menu" role="dialog" [id]="fieldId()+'-panel'" [attr.aria-label]="label()" (keydown.escape)="close($event)">
        <input #search type="search" role="searchbox" autocomplete="off" [attr.aria-label]="'Pesquisar '+label()" placeholder="Pesquisar" [value]="query()" (input)="filter($event)" (keydown.enter)="$event.preventDefault();$event.stopPropagation()">
        <div class="multi-select-actions"><button type="button" class="text-button" [disabled]="disabled()||!options().length" (click)="selectAll()">Select All</button><button type="button" class="text-button" [disabled]="disabled()||!value().length" (click)="clearAll()">Clear All</button></div>
        <p class="help">Select All e Clear All aplicam-se a todas as opções, mesmo com pesquisa ativa.</p>
        <ul [attr.aria-label]="label()">
          @for(option of matches();track option.value;let index=$index){<li class="multi-select-option"><label [for]="fieldId()+'-choice-'+index" (pointerdown)="retainOptionFocus($event)"><input [id]="fieldId()+'-choice-'+index" type="checkbox" [checked]="value().includes(option.value)" [disabled]="disabled()" (change)="select(option.value,$event)" (keydown.enter)="$event.preventDefault();$event.stopPropagation()"><span>{{option.label}}</span></label></li>}
        </ul>
        @if(!options().length){<p role="status">{{emptyMessage()}}</p>}
        @else if(!matches().length){<p role="status">{{noResultsMessage()}}</p>}
      </div>
    }
  </div>
  @if(selectedLabels().length){<p class="help multi-select-summary">Selecionadas: {{selectedLabels().join(', ')}}</p>}
`})
export class MultiSelect {
  readonly fieldId=input.required<string>();readonly label=input('Opções');readonly choices=input<readonly SelectOption[]>([]);
  readonly placeholder=input('Selecione opções');readonly selectedCountLabel=input('opções selecionadas');readonly emptyMessage=input('Nenhuma opção disponível.');readonly noResultsMessage=input('Nenhum resultado encontrado.');
  readonly value=model<string[]>([]);readonly disabled=input(false);readonly describedBy=input('');readonly error=input('');
  readonly open=signal(false);readonly query=signal('');
  readonly options=computed(()=>[...new Map(this.choices().map(option=>[option.value,option] as const)).values()]);
  readonly matches=computed(()=>filterSelectOptions(this.options(),this.query()));
  readonly selectedLabels=computed(()=>this.options().filter(option=>this.value().includes(option.value)).map(option=>option.label));
  readonly summary=computed(()=>this.value().length===1&&this.selectedLabels().length?this.selectedLabels()[0]:this.value().length?this.value().length+' '+this.selectedCountLabel():this.placeholder());
  private readonly host=inject(ElementRef<HTMLElement>);private readonly injector=inject(Injector);
  private readonly trigger=viewChild.required<ElementRef<HTMLButtonElement>>('trigger');private readonly search=viewChild<ElementRef<HTMLInputElement>>('search');
  constructor(){effect(()=>{if(this.disabled())this.open.set(false);});}
  show():void{if(this.disabled())return;this.open.set(true);afterNextRender(()=>this.search()?.nativeElement.focus(),{injector:this.injector});}
  toggle():void{if(this.open())this.open.set(false);else this.show();}
  filter(event:Event):void{this.query.set((event.target as HTMLInputElement).value);}
  retainOptionFocus(event:PointerEvent):void{
    // Prevent focusout from removing the label before its native click activates the checkbox.
    // Direct checkbox interaction and keyboard focus retain their normal behavior.
    if(event.button===0&&event.target instanceof Element&&!event.target.closest('input'))event.preventDefault();
  }
  select(id:string,event:Event):void{if(this.disabled()||!this.options().some(option=>option.value===id))return;const checked=(event.target as HTMLInputElement).checked;this.value.set(checked?uniqueSelectValues([...this.value(),id]):this.value().filter(value=>value!==id));}
  selectAll():void{if(!this.disabled())this.value.set(uniqueSelectValues(this.options().map(option=>option.value)));}
  clearAll():void{if(!this.disabled())this.value.set([]);}
  close(event:Event):void{if(!this.open())return;event.preventDefault();event.stopPropagation();this.open.set(false);this.trigger().nativeElement.focus();}
  leave(event:FocusEvent):void{if(!this.host.nativeElement.contains(event.relatedTarget as Node|null))this.open.set(false);}
  @HostListener('document:click',['$event']) outside(event:MouseEvent):void{if(event.target instanceof Node&&!this.host.nativeElement.contains(event.target))this.open.set(false);}
}

import { Component, computed, input, output } from '@angular/core';
import { Resource, RegistrationResource } from '../catalogue/models';
import { ResourceTabs } from './resource-tabs';

/** Navigation only: the registration owner handles forms and unsaved-change decisions. */
@Component({selector:'app-registration-navigation',imports:[ResourceTabs],template:`
  <app-resource-tabs [selected]="main()" [disabled]="disabled()" (selectedChange)="selectedChange.emit($event)" />
  @if(main()==='tags'){
    <div class="registration-submenu equal-width-options" role="group" aria-label="Cadastros de Tag">
      <button type="button" [class.selected]="selected()==='tags'" [attr.aria-pressed]="selected()==='tags'" [disabled]="disabled()" (click)="selectedChange.emit('tags')">Tag</button>
      <button type="button" [class.selected]="selected()==='tag_categories'" [attr.aria-pressed]="selected()==='tag_categories'" [disabled]="disabled()" (click)="selectedChange.emit('tag_categories')">Categoria de Tag</button>
    </div>
  }
`})
export class RegistrationNavigation {
  readonly selected=input<RegistrationResource>('platforms');readonly disabled=input(false);readonly selectedChange=output<RegistrationResource>();
  readonly main=computed<Resource>(()=>{const selected=this.selected();return selected==='tag_categories'?'tags':selected;});
}

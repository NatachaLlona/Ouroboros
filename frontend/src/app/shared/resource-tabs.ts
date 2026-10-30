import { Component, input, output } from '@angular/core';
import { resources } from '../catalogue/resources';
import { Resource } from '../catalogue/models';
@Component({selector:'app-resource-tabs',template:`<div class="type-picker" role="group" aria-label="Tipo de item">@for(option of options;track option.resource){<button type="button" class="type-option" [class.selected]="selected()===option.resource" [attr.aria-pressed]="selected()===option.resource" [disabled]="disabled()" (click)="selectedChange.emit(option.resource)">{{option.label}}</button>}</div>`})
export class ResourceTabs {readonly options=resources;readonly selected=input<Resource>('platforms');readonly selectedChange=output<Resource>();readonly disabled=input(false);}

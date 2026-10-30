import { Component, inject, input } from '@angular/core';
import { form, FormField, required, pattern, maxLength } from '@angular/forms/signals';
import { Drafts } from './drafts';
import { FieldError } from './field-error';
import { DescriptionInput } from '../shared/description-input';
import { FieldLabel, FANTASY_NAME_LABEL, FANTASY_NAME_HELP_TEXT } from '../shared/field-label';
@Component({ selector: 'app-classification-form', imports: [FormField, FieldError, FieldLabel,DescriptionInput], template: `
  <div class="field"><app-field-label fieldId="work_classification_name" label="Nome técnico" help="Minúsculas sem acentos, números e underscores entre palavras. O nome não será alterado." [required]="true" /><input id="work_classification_name" [formField]="fields.work_classification_name" aria-describedby="work_classification_name-help work_classification_name-error"><app-field-error name="work_classification_name" [error]="error()" /></div>
  <div class="field"><app-field-label fieldId="display_name_work_classifications" [label]="nameLabel" [help]="nameHelp" [required]="true" /><input id="display_name_work_classifications" [formField]="fields.display_name_work_classifications" aria-describedby="display_name_work_classifications-help display_name_work_classifications-error"><app-field-error name="display_name_work_classifications" [error]="error()" /></div>
  <div class="field"><app-field-label fieldId="description_work_classifications" label="Descrição" [required]="false" /><app-description-input fieldId="description_work_classifications" [formField]="fields.description_work_classifications" /><app-field-error name="description_work_classifications" [error]="error()" /></div>
  <div class="field"><app-field-label fieldId="tier" label="Posição (tier)" help="Vazio: adicionar no fim. Com uma posição: o servidor insere e reordena as restantes classificações numa transação." [required]="false" /><input id="tier" inputmode="numeric" [formField]="fields.tier" aria-describedby="tier-help tier-error"><app-field-error name="tier" [error]="error()" /></div>
` })
export class ClassificationForm {
  readonly nameLabel=FANTASY_NAME_LABEL;readonly nameHelp=FANTASY_NAME_HELP_TEXT;
  readonly error = input<unknown>();
  readonly fields = form(inject(Drafts).classification, path => { required(path.work_classification_name); pattern(path.work_classification_name, /^[a-z][a-z0-9]*(_[a-z0-9]+)*$/); pattern(path.tier, /^(?:[1-9][0-9]*)?$/); required(path.display_name_work_classifications); });
}

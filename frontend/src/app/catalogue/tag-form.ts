import { Component, inject, input } from '@angular/core';
import { form, FormField, required, pattern, maxLength } from '@angular/forms/signals';
import { Drafts } from './drafts';
import { FieldError } from './field-error';
import { DescriptionInput } from '../shared/description-input';
import { FieldLabel, FANTASY_NAME_LABEL, FANTASY_NAME_HELP_TEXT } from '../shared/field-label';
@Component({ selector: 'app-tag-form', imports: [FormField, FieldError, FieldLabel,DescriptionInput], template: `
  <div class="field"><app-field-label fieldId="tag_name" label="Nome técnico" help="Minúsculas sem acentos, números e underscores entre palavras. Ex.: fantasia_epica. O nome não será alterado." [required]="true" /><input id="tag_name" [formField]="fields.tag_name" aria-describedby="tag_name-help tag_name-error"><app-field-error name="tag_name" [error]="error()" /></div>
  <div class="field"><app-field-label fieldId="display_name_tags" [label]="nameLabel" [help]="nameHelp" [required]="true" /><input id="display_name_tags" [formField]="fields.display_name_tags" aria-describedby="display_name_tags-help display_name_tags-error"><app-field-error name="display_name_tags" [error]="error()" /></div>
  <div class="field"><app-field-label fieldId="description_tags" label="Descrição" [required]="false" /><app-description-input fieldId="description_tags" [formField]="fields.description_tags" /><app-field-error name="description_tags" [error]="error()" /></div>
` })
export class TagForm {
  readonly nameLabel=FANTASY_NAME_LABEL;readonly nameHelp=FANTASY_NAME_HELP_TEXT;
  readonly error = input<unknown>();
  readonly fields = form(inject(Drafts).tag, path => { required(path.tag_name); pattern(path.tag_name, /^[a-z][a-z0-9]*(_[a-z0-9]+)*$/); required(path.display_name_tags); });
}

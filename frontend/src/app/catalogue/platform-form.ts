import { Component, inject, input } from '@angular/core';
import { form, FormField, required, pattern, maxLength } from '@angular/forms/signals';
import { Drafts } from './drafts';
import { FieldError } from './field-error';
import { FieldLabel, FANTASY_NAME_LABEL, FANTASY_NAME_HELP_TEXT, PRICE_HELP_TEXT } from '../shared/field-label';
@Component({ selector: 'app-platform-form', imports: [FormField, FieldError, FieldLabel], template: `
  <div class="field"><app-field-label fieldId="platform_name" [label]="nameLabel" [help]="nameHelp" [required]="true" /><input id="platform_name" [formField]="fields.platform_name" aria-describedby="platform_name-help platform_name-error"><app-field-error name="platform_name" [error]="error()" /></div>
  <fieldset><legend>Como funciona?</legend><div class="check-grid">
  <div><app-field-label fieldId="legacy-platform-paid" label="Plataforma paga" help="Desmarcada: gratuita. O preço pode continuar desconhecido." /><input id="legacy-platform-paid" type="checkbox" [formField]="fields.platform_is_paid" aria-describedby="legacy-platform-paid-help"></div>
  <label class="check"><input type="checkbox" [formField]="fields.platform_is_episodes">Conteúdo em episódios</label>
  <label class="check"><input type="checkbox" [formField]="fields.platform_is_duration_time">Conteúdo com duração</label></div></fieldset>
  <div class="field-grid"><div class="field"><app-field-label fieldId="price_amount" label="Preço" [help]="priceHelp" [required]="false" /><input id="price_amount" inputmode="decimal" [formField]="fields.price_amount" aria-describedby="price_amount-help price_amount-error"><app-field-error name="price_amount" [error]="error()" /></div>
  <div class="field"><app-field-label fieldId="price_currency" label="Moeda" help="Por exemplo, EUR." [required]="false" /><input id="price_currency" [formField]="fields.price_currency" aria-describedby="price_currency-help price_currency-error"><app-field-error name="price_currency" [error]="error()" /></div></div>
  <fieldset aria-describedby="legacy-access-help"><legend><app-field-label fieldId="legacy-access" label="Onde aceder?" help="Pode escolher várias opções. Nenhuma seleção: sem informação." /></legend><div class="access-grid" id="legacy-access">
  <label class="check"><input type="checkbox" [formField]="fields.application">Aplicação</label><label class="check"><input type="checkbox" [formField]="fields.website">Website</label><label class="check"><input type="checkbox" [formField]="fields.link">Link</label></div><app-field-error name="platform_access_types" [error]="error()" /></fieldset>
  <div class="field"><app-field-label fieldId="platform_url" label="Endereço da plataforma" help="Use http:// ou https://, até 2083 caracteres." [required]="false" /><input id="platform_url" type="url" [formField]="fields.platform_url" aria-describedby="platform_url-help platform_url-error"><app-field-error name="platform_url" [error]="error()" /></div>
` })
export class PlatformForm {
  readonly priceHelp=PRICE_HELP_TEXT;
  readonly nameLabel=FANTASY_NAME_LABEL;readonly nameHelp=FANTASY_NAME_HELP_TEXT;
  readonly error = input<unknown>();
  readonly fields = form(inject(Drafts).platform, path => { required(path.platform_name); maxLength(path.platform_url, 2083); });
}

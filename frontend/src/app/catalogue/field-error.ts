import { Component, input } from '@angular/core';
import { ApiError } from '../shared/api';
export function hasFieldError(error: unknown, name: string): boolean {
  return error instanceof ApiError && error.details.some(detail => detail.loc?.includes(name));
}
@Component({ selector: 'app-field-error', template: `<p class="field-error" [id]="name() + '-error'">{{ hasError() ? 'Reveja este campo de acordo com a indicação acima.' : '' }}</p>` })
export class FieldError {
  readonly name = input.required<string>();
  readonly error = input<unknown>();
  hasError(): boolean { return hasFieldError(this.error(), this.name()); }
}

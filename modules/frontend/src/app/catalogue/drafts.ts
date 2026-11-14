import { Injectable, signal } from '@angular/core';
import { emptyPlatform, emptyTag, emptyClassification } from './models';
// Page-scoped DI lifetime: drafts survive session expiry/type changes, never navigation/storage.
@Injectable()
export class Drafts {
  readonly platform = signal(emptyPlatform());
  readonly tag = signal(emptyTag());
  readonly classification = signal(emptyClassification());
}

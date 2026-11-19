import { Component, ElementRef, Injector, OnChanges, afterNextRender, inject, input, viewChild } from '@angular/core';
@Component({ selector: 'app-notice', template: `<p #message class="notice" role="status" tabindex="-1">{{ text() }}</p>` })
export class Notice implements OnChanges {
  readonly text = input.required<string>();
  readonly activation = input(0);
  private readonly injector = inject(Injector);
  private readonly message = viewChild.required<ElementRef<HTMLElement>>('message');
  ngOnChanges(): void {
    afterNextRender(() => { const element = this.message().nativeElement; element.focus({ preventScroll: true }); element.scrollIntoView({ block: 'center' }); }, { injector: this.injector });
  }
}

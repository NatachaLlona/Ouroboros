import { Component, DestroyRef, ElementRef, afterNextRender, inject, signal, viewChild } from '@angular/core';
import { form, FormField, required } from '@angular/forms/signals';
import { Router } from '@angular/router';
import { Session } from './session';
import { FieldLabel } from '../shared/field-label';
import { ApiError, safeMessage } from '../shared/api';
@Component({ selector: 'app-login', imports: [FormField,FieldLabel], template: `
  <dialog #dialog class="modal" aria-labelledby="login-title" aria-describedby="login-intro" (cancel)="cancel($event)">
  <div class="modal-content"><div class="modal-top"><img src="/frontend/assets/mark.svg" alt="" width="43" height="43"><button class="icon-button" type="button" [disabled]="busy()" (click)="close()" aria-label="Fechar início de sessão">×</button></div>
  <p class="eyebrow">O SEU UNIVERSO ESTÁ À ESPERA</p><h2 id="login-title">Que bom ter-vos<br>por aqui.</h2>
  <p id="login-intro" class="modal-intro">Entre com a sua conta Ouroboros para continuar.<br>Use a conta da aplicação, não a da base de dados.</p>
  <form (submit)="submit($event)"><p class="required-note"><strong class="required-star" aria-hidden="true">*</strong> Campo obrigatório</p><fieldset [disabled]="busy()"><div class="field"><app-field-label fieldId="login-username" label="Nome de utilizador" [required]="true" /><input #username id="login-username" autocomplete="username" aria-required="true" [formField]="fields.username"></div>
  <div class="field"><app-field-label fieldId="login-password" label="Palavra-passe" [required]="true" /><div class="password-wrap"><input id="login-password" [type]="showPassword() ? 'text' : 'password'" autocomplete="current-password" aria-required="true" [formField]="fields.password"><button class="icon-button password-toggle" type="button" (click)="showPassword.set(!showPassword())" [attr.aria-pressed]="showPassword()" [attr.aria-label]="showPassword() ? 'Ocultar palavra-passe' : 'Mostrar palavra-passe'"><svg aria-hidden="true" viewBox="0 0 24 24" width="22" height="22"><path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z" fill="none" stroke="currentColor" stroke-width="1.7"/><circle cx="12" cy="12" r="3" fill="none" stroke="currentColor" stroke-width="1.7"/>@if(showPassword()){<path d="m3 3 18 18" stroke="currentColor" stroke-width="2"/>}</svg></button></div></div></fieldset>
  <p class="form-error" role="alert">{{ error() || session.loginReason() }}</p>
  @if (remaining()) { <p role="status">Aguarde {{ remaining() }} segundos antes de tentar novamente.</p> }
  <button class="button button-primary" [disabled]="busy() || remaining() > 0" type="submit">{{ busy() ? 'A entrar…' : 'Entrar' }} ↗</button></form>
  <p class="modal-note">Uma sessão segura. As suas histórias continuam consigo.</p></div></dialog>
` })
export class Login {
  readonly session = inject(Session);
  private readonly router = inject(Router);
  readonly model = signal({ username: '', password: '' });
  readonly fields = form(this.model, path => { required(path.username); required(path.password); });
  readonly busy = signal(false);
  readonly showPassword = signal(false);
  readonly error = signal('');
  readonly remaining = signal(0);
  private readonly dialog = viewChild.required<ElementRef<HTMLDialogElement>>('dialog');
  private readonly username = viewChild.required<ElementRef<HTMLInputElement>>('username');
  private readonly previousFocus = document.activeElement as HTMLElement | null;
  private timer?: ReturnType<typeof setInterval>;
  constructor() {
    afterNextRender(() => { this.dialog().nativeElement.showModal(); this.username().nativeElement.focus(); });
    inject(DestroyRef).onDestroy(() => { clearInterval(this.timer); this.model.set({ username: '', password: '' }); this.previousFocus?.focus(); });
  }
  cancel(event: Event): void { event.preventDefault(); if (!this.busy()) this.close(); }
  close(): void { this.model.update(value => ({ ...value, password: '' })); this.session.loginOpen.set(false); }
  async submit(event: Event): Promise<void> {
    event.preventDefault();
    if (this.busy() || this.remaining() || this.fields().invalid()) return;
    this.busy.set(true); this.error.set('');
    const { username, password } = this.model();
    this.model.update(value => ({ ...value, password: '' }));
    try {
      await this.session.login(username, password);
      this.close();
      const destination=this.session.returnUrl();
      if (this.router.url.split('?')[0] !== destination) await this.router.navigateByUrl(destination);
    } catch (error) {
      this.error.set(safeMessage(error));
      if (error instanceof ApiError && error.status === 429) {
        const parsed = Number(error.retryAfter) || Math.ceil((Date.parse(error.retryAfter) - Date.now()) / 1000) || 300;
        const until = Date.now() + Math.min(86400, Math.max(1, parsed)) * 1000;
        const tick = () => { this.remaining.set(Math.max(0, Math.ceil((until - Date.now()) / 1000))); if (!this.remaining()) clearInterval(this.timer); };
        tick(); this.timer = setInterval(tick, 1000);
      }
    } finally { this.busy.set(false); }
  }
}

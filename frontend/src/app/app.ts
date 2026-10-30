import { Component, inject, signal } from '@angular/core';
import { Router, RouterLink, RouterOutlet } from '@angular/router';
import { Session } from './auth/session';
import { Login } from './auth/login';
import { safeMessage } from './shared/api';
import { Notice } from './shared/notice';
import { Confirmation } from './shared/confirmation';
import { UnsavedChanges } from './shared/unsaved-changes';
@Component({ selector: 'app-root', imports: [RouterLink, RouterOutlet, Login, Notice, Confirmation], template: `
  <a class="skip-link" href="#main">Ir para o conteúdo</a>
  <header class="site-header"><a class="brand" routerLink="/" aria-label="Ouroboros, início"><img src="/frontend/assets/mark.svg" alt="" width="39" height="39">Ouroboros</a>
  <nav aria-label="Conta"><span class="account-name" data-account>{{ session.current().username }}</span>
  @if (session.current().authenticated) { <button class="text-button" [disabled]="busy()" (click)="logout()">{{ busy() ? 'A sair…' : 'Sair' }} ↗</button> }
  @else { <button class="text-button" (click)="session.openLogin()">Entrar ↗</button> }</nav></header>
  @if (error()) { <app-notice [text]="error()" /> }
  <router-outlet />
  <footer class="site-footer"><span>OUROBOROS / O seu universo, em ordem.</span><span>Um capítulo de cada vez. <span class="footer-build" title="Identificador do build desta página">Interface {{buildId}}</span></span></footer>
  @if (session.loginOpen()) { <app-login /> }
  @if(unsaved.asking()){<app-confirmation title="Descartar alterações não salvas?" name="Você pode cancelar e continuar editando." action="Descartar alterações" cancelLabel="Cancelar e continuar editando" (cancelled)="unsaved.decide(false)" (confirmed)="unsaved.decide(true)" />}
` })
export class App {
  readonly session = inject(Session);
  readonly buildId=document.querySelector<HTMLMetaElement>('meta[name="ouroboros-build"]')?.content||'não identificada';
  readonly unsaved=inject(UnsavedChanges);
  private readonly router = inject(Router);
  readonly busy = signal(false);
  readonly error = signal('');
  async logout(): Promise<void> {
    if (this.busy()) return;
    this.busy.set(true); this.error.set('');
    try { if(!await this.unsaved.allowExit())return;await this.session.logout(); await this.router.navigateByUrl('/'); }
    catch (error) { this.error.set(safeMessage(error)); }
    finally { this.busy.set(false); }
  }
}

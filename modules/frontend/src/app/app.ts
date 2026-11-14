import { Component, inject, signal } from '@angular/core';
import { Router, RouterLink, RouterOutlet } from '@angular/router';
import { Session } from './auth/session';
import { Login } from './auth/login';
import { safeMessage } from './shared/api';
import { Notice } from './shared/notice';
import { Confirmation } from './shared/confirmation';
import { UnsavedChanges } from './shared/unsaved-changes';
import { SiteAssistant } from './shared/site-assistant';
@Component({ selector: 'app-root', imports: [RouterLink, RouterOutlet, Login, Notice, Confirmation, SiteAssistant], template: `
  <a class="skip-link" href="#main">Skip to content</a>
  <header class="site-header"><a class="brand" routerLink="/" aria-label="Ouroboros, home"><img src="/frontend/assets/mark.svg" alt="" width="39" height="39">Ouroboros</a>
  <nav aria-label="Account"><span class="account-name" data-account>{{ session.current().username }}</span>
  @if (session.current().authenticated) { <button class="text-button" [disabled]="busy()" (click)="logout()">{{ busy() ? 'Signing out…' : 'Sign out' }} ↗</button> }
  @else { <button class="text-button" (click)="session.openLogin()">Sign in ↗</button> }</nav></header>
  @if (error()) { <app-notice [text]="error()" /> }
  <router-outlet />
  <app-site-assistant />
  <footer class="site-footer"><span>OUROBOROS / Your universe, in order.</span><span>One chapter at a time. <span class="footer-build" title="Build identifier for this page">Interface {{buildId}}</span></span></footer>
  @if (session.loginOpen()) { <app-login /> }
  @if(unsaved.asking()){<app-confirmation title="Discard unsaved changes?" name="You can cancel and keep editing." action="Discard changes" cancelLabel="Cancel and keep editing" (cancelled)="unsaved.decide(false)" (confirmed)="unsaved.decide(true)" />}
` })
export class App {
  readonly session = inject(Session);
  readonly buildId=document.querySelector<HTMLMetaElement>('meta[name="ouroboros-build"]')?.content||'unidentified';
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

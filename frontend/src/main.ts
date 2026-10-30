import { bootstrapApplication } from '@angular/platform-browser';
import { provideHttpClient, withNoXsrfProtection } from '@angular/common/http';
import { provideRouter } from '@angular/router';
import { App } from './app/app';
import { leaveRegistration } from './app/shared/unsaved-changes';

// CSRF uses the existing synchronizer token, not Angular's cookie-based default.
bootstrapApplication(App, { providers: [provideHttpClient(withNoXsrfProtection()), provideRouter([
  { path: '', pathMatch: 'full', loadComponent: () => import('./app/home/home').then(m => m.Home) },
  { path: 'cadastrar', loadComponent: () => import('./app/catalogue/selection').then(m => m.Selection) },
  { path: 'consultar', data:{consulting:true}, loadComponent: () => import('./app/catalogue/selection').then(m => m.Selection) },
  { path: 'consultas', loadComponent: () => import('./app/catalogue/consultation').then(m => m.Consultation) },
  { path: 'cadastros', canDeactivate:[leaveRegistration], loadComponent: () => import('./app/catalogue/registration').then(m => m.Registration) }
])] }).catch(() => { document.body.textContent = 'Não foi possível abrir a aplicação. Atualize a página ou contacte o administrador.'; });

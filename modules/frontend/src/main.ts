import { bootstrapApplication } from '@angular/platform-browser';
import { provideHttpClient, withNoXsrfProtection } from '@angular/common/http';
import { provideRouter } from '@angular/router';
import { App } from './app/app';
import { leaveRegistration } from './app/shared/unsaved-changes';
import { loadFrontendConfig } from './app/configuration';

// CSRF uses the existing synchronizer token, not Angular's cookie-based default.
loadFrontendConfig().then(()=>bootstrapApplication(App, { providers: [provideHttpClient(withNoXsrfProtection()), provideRouter([
  { path: '', pathMatch: 'full', loadComponent: () => import('./app/home/home').then(m => m.Home) },
  { path: 'create', loadComponent: () => import('./app/catalogue/selection').then(m => m.Selection) },
  { path: 'browse', data:{consulting:true}, loadComponent: () => import('./app/catalogue/selection').then(m => m.Selection) },
  { path: 'catalogue', loadComponent: () => import('./app/catalogue/consultation').then(m => m.Consultation) },
  { path: 'registrations', canDeactivate:[leaveRegistration], loadComponent: () => import('./app/catalogue/registration').then(m => m.Registration) },
  { path: 'cadastrar', redirectTo: 'create', pathMatch: 'full' },
  { path: 'consultar', redirectTo: 'browse', pathMatch: 'full' },
  { path: 'consultas', redirectTo: 'catalogue', pathMatch: 'full' },
  { path: 'cadastros', redirectTo: 'registrations', pathMatch: 'full' }
])] })).catch(() => { document.body.textContent = 'Could not open the application. Refresh the page or contact an administrator.'; });

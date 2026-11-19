import { Component, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { Session } from '../auth/session';
import { safeMessage } from '../shared/api';
import { Notice } from '../shared/notice';
@Component({selector:'app-home',imports:[RouterLink,Notice],template:`
  <main id="main" class="home-main"><section class="hero" aria-labelledby="hero-title"><div><p class="eyebrow">YOUR PERSONAL CATALOGUE</p><h1 id="hero-title">Stories that stay.<br><em>A place for every one.</em></h1></div><p class="hero-note">Between pages, screens and other worlds.<br>One chapter at a time.</p></section>
  @if(error()){<app-notice [text]="error()" />}
  <section class="actions primary-actions" aria-label="Where would you like to start?">
    <article class="action-card featured"><a class="card-image image-link" [routerLink]="destinations.create" aria-label="Create"><img src="/frontend/assets/little-universe.svg" alt="A collection of books and a friendly snake" width="480" height="350"></a><div class="card-copy"><h2>Create</h2><p>Add the pieces of your universe.</p><a class="button button-primary" [routerLink]="destinations.create">Create ↗</a></div></article>
    <article class="action-card"><a class="card-image image-link" [routerLink]="destinations.consult" aria-label="Browse"><img src="/frontend/assets/kept-stories.svg" alt="A projector among stars" width="480" height="350"></a><div class="card-copy"><h2>Browse</h2><p>Find the stories you have saved.</p><a class="button button-primary" [routerLink]="destinations.consult">Browse ↗</a></div></article>
  </section></main>
`})
export class Home {
  readonly destinations={create:'/create',consult:'/browse'} as const;
  private readonly session=inject(Session);private readonly router=inject(Router);readonly error=signal('');
  constructor(){void this.initialize();}
  private async initialize():Promise<void>{
    try{await this.session.ensure();const query=new URLSearchParams(location.search);
      if(query.has('sign_in')||query.has('entrar')){const destination=['catalogue','consultas'].includes(query.get('destination')||query.get('destino')||'')?'/catalogue':'/registrations';
        if(this.session.canCreate())await this.router.navigateByUrl(destination);else this.session.openLogin('Sign in to continue.',destination);}
    }catch(error){this.error.set(safeMessage(error));}
  }
}

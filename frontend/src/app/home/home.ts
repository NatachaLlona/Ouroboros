import { Component, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { Session } from '../auth/session';
import { safeMessage } from '../shared/api';
import { Notice } from '../shared/notice';
@Component({selector:'app-home',imports:[RouterLink,Notice],template:`
  <main id="main" class="home-main"><section class="hero" aria-labelledby="hero-title"><div><p class="eyebrow">O SEU CATÁLOGO PESSOAL</p><h1 id="hero-title">Histórias que ficam.<br><em>Um lugar para cada uma.</em></h1></div><p class="hero-note">Entre páginas, ecrãs e outros mundos.<br>Um capítulo de cada vez.</p></section>
  @if(error()){<app-notice [text]="error()" />}
  <section class="actions primary-actions" aria-label="Por onde deseja começar?">
    <article class="action-card featured"><div class="card-image"><img src="/frontend/assets/little-universe.svg" alt="Uma coleção de livros e uma serpente amigável" width="480" height="350"></div><div class="card-copy"><h2>Cadastrar</h2><p>Adicione as peças do seu universo.</p><a class="button button-primary" routerLink="/cadastrar">Cadastrar ↗</a></div></article>
    <article class="action-card"><div class="card-image"><img src="/frontend/assets/kept-stories.svg" alt="Um projetor entre estrelas" width="480" height="350"></div><div class="card-copy"><h2>Consultar</h2><p>Encontre as histórias que já guardou.</p><a class="button button-primary" routerLink="/consultar">Consultar ↗</a></div></article>
  </section></main>
`})
export class Home {
  private readonly session=inject(Session);private readonly router=inject(Router);readonly error=signal('');
  constructor(){void this.initialize();}
  private async initialize():Promise<void>{
    try{await this.session.ensure();const query=new URLSearchParams(location.search);
      if(query.has('entrar')){const destination=query.get('destino')==='consultas'?'/consultas':'/cadastros';
        if(this.session.canCreate())await this.router.navigateByUrl(destination);else this.session.openLogin('Entre para continuar.',destination);}
    }catch(error){this.error.set(safeMessage(error));}
  }
}

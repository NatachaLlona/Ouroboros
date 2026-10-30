import { Component, input } from '@angular/core';
import { RouterLink } from '@angular/router';
@Component({selector:'app-catalogue-layout',imports:[RouterLink],template:`
  <main id="main" class="entry-main"><div class="page-links"><a class="back-link" [class.home-return]="platformRegistration()" [routerLink]="back()">← {{ backLabel() }}</a>@if(!platformRegistration()){<a class="back-link home-return" routerLink="/">← Voltar ao início</a>}</div>
  <div class="entry-heading"><p class="eyebrow">AS PEÇAS DO SEU UNIVERSO</p><h1>{{ title() }}</h1><p>{{ subtitle() }}</p></div>
  <div class="entry-layout" [class.list-layout]="wide()"><section class="form-panel"><ng-content /></section>
  @if (!wide()) { <aside class="mascot-panel"><span class="eyebrow">PEQUENOS DETALHES, GRANDES HISTÓRIAS</span><img src="/frontend/assets/snake.svg" alt="Uma serpente simpática junto de livros" width="440" height="410"><h2>O seu universo<br>ganha forma.</h2><p>Um capítulo de cada vez.</p></aside> }</div></main>
`})
export class CatalogueLayout { readonly platformRegistration=input(false);readonly title=input.required<string>();readonly subtitle=input('');readonly back=input('/');readonly backLabel=input('Voltar');readonly wide=input(false); }

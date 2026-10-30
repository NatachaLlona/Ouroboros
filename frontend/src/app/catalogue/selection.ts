import { Component, inject } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { SelectionCards } from '../shared/selection-cards';
@Component({selector:'app-selection',imports:[SelectionCards,RouterLink],template:`
  <main id="main" class="home-main"><a class="back-link home-return" routerLink="/">← Voltar ao início</a>
    <section class="hero"><div><p class="eyebrow">O SEU UNIVERSO, EM ORDEM</p><h1>{{consulting?'Consultar':'Cadastrar'}}</h1><p>Escolha por onde continuar.</p></div></section>
    <app-selection-cards [consulting]="consulting" />
  </main>
`})
export class Selection {readonly consulting=inject(ActivatedRoute).snapshot.data['consulting']===true;}

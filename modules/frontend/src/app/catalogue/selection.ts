import { Component, inject } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { SelectionCards } from '../shared/selection-cards';
@Component({selector:'app-selection',imports:[SelectionCards,RouterLink],template:`
  <main id="main" class="home-main"><a class="back-link home-return" routerLink="/">← Back to home</a>
    <section class="hero"><div><p class="eyebrow">YOUR UNIVERSE, IN ORDER</p><h1>{{consulting?'Browse':'Create'}}</h1><p>Choose where to continue.</p></div></section>
    <app-selection-cards [consulting]="consulting" />
  </main>
`})
export class Selection {readonly consulting=inject(ActivatedRoute).snapshot.data['consulting']===true;}

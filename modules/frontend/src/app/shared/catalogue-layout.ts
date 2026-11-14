import { Component, input } from '@angular/core';
import { RouterLink } from '@angular/router';
@Component({selector:'app-catalogue-layout',imports:[RouterLink],template:`
  <main id="main" class="entry-main"><div class="page-links" [class.page-links-single]="singleBackLink()"><a class="back-link" [class.home-return]="singleBackLink()" [routerLink]="back()">← {{ backLabel() }}</a>@if(!singleBackLink()){<a class="back-link home-return" routerLink="/">← Back to home</a>}</div>
  <div class="entry-heading"><p class="eyebrow">THE PIECES OF YOUR UNIVERSE</p><h1>{{ title() }}</h1><p>{{ subtitle() }}</p></div>
  <div class="entry-layout" [class.list-layout]="wide()"><section class="form-panel"><ng-content /></section>
  @if (!wide()) { <aside class="mascot-panel"><span class="eyebrow">SMALL DETAILS, GREAT STORIES</span><img src="/frontend/assets/snake.svg" alt="A friendly snake beside books" width="440" height="410"><h2>Your universe<br>takes shape.</h2><p>One chapter at a time.</p></aside> }</div></main>
`})
export class CatalogueLayout { readonly singleBackLink=input(false);readonly title=input.required<string>();readonly subtitle=input('');readonly back=input('/');readonly backLabel=input('Back');readonly wide=input(false); }

import { Component, input } from '@angular/core';
import { RouterLink } from '@angular/router';

/** The same choices and navigation are used for creation and consultation. */
@Component({selector:'app-selection-cards',imports:[RouterLink],template:`
  <section class="actions" aria-label="Choose an area">
    @for(card of cards;track card.name){
      <article class="action-card" [class.featured]="card.enabled">
      @if(card.enabled){<a class="card-image image-link" [routerLink]="destination()" [attr.aria-label]="consulting()?'Browse individual items':'Create item'"><img [src]="'/frontend/assets/'+card.image" alt="" width="480" height="350"></a>}
      @else{<div class="card-image"><img [src]="'/frontend/assets/'+card.image" alt="" width="480" height="350"></div>}
      <div class="card-copy"><h2>{{card.enabled&&!consulting()?'Create item':verb()+' '+card.name}}</h2>
        @if(card.enabled){<a class="button button-primary" [routerLink]="destination()">{{consulting()?'Browse individual items':'Create item'}} ↗</a>}
        @else{<button class="button button-disabled" disabled [attr.aria-label]="verb()+' '+card.name+' — coming soon'">Coming soon ↗</button>}
      </div></article>
    }
  </section>
`})
export class SelectionCards {
  readonly consulting=input(false);
  readonly cards=[{name:'Watched',image:'kept-stories.svg',enabled:false},{name:'Watchlist',image:'next-chapter.svg',enabled:false},{name:'individual items',image:'little-universe.svg',enabled:true}];
  destination():string{return this.consulting()?'/catalogue':'/registrations';}
  verb():string{return this.consulting()?'Browse':'Create';}
}

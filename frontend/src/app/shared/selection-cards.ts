import { Component, input } from '@angular/core';
import { RouterLink } from '@angular/router';

/** The same choices and navigation are used for creation and consultation. */
@Component({selector:'app-selection-cards',imports:[RouterLink],template:`
  <section class="actions" aria-label="Escolha uma área">
    @for(card of cards;track card.name){
      <article class="action-card" [class.featured]="card.enabled"><div class="card-image"><img [src]="'/frontend/assets/'+card.image" alt="" width="480" height="350"></div>
      <div class="card-copy"><h2>{{card.enabled&&!consulting()?'Cadastrar item':verb()+' '+card.name}}</h2>
        @if(card.enabled){<a class="button button-primary" [routerLink]="consulting()?'/consultas':'/cadastros'">{{consulting()?'Consultar itens isolados':'Cadastrar item'}} ↗</a>}
        @else{<button class="button button-disabled" disabled [attr.aria-label]="verb()+' '+card.name+' — em breve'">Em breve ↗</button>}
      </div></article>
    }
  </section>
`})
export class SelectionCards {
  readonly consulting=input(false);
  readonly cards=[{name:'Watched',image:'kept-stories.svg',enabled:false},{name:'Watchlist',image:'next-chapter.svg',enabled:false},{name:'itens isolados',image:'little-universe.svg',enabled:true}];
  verb():string{return this.consulting()?'Consultar':'Cadastrar';}
}

import { Component, computed, input, output } from '@angular/core';
@Component({selector:'app-pagination',template:`<nav class="pagination" aria-label="Paginação"><button class="button" type="button" [disabled]="busy()||page()<=1" (click)="changed.emit(page()-1)">Anterior</button><span aria-live="polite">Página {{page()}} de {{pages()}} · {{count()}} itens</span><button class="button" type="button" [disabled]="busy()||page()>=pages()" (click)="changed.emit(page()+1)">Seguinte</button></nav>`})
export class Pagination {
  readonly page=input(1);readonly count=input(0);readonly size=input(10);readonly busy=input(false);readonly changed=output<number>();
  readonly pages=computed(()=>Math.max(1,Math.ceil(this.count()/this.size())));
}

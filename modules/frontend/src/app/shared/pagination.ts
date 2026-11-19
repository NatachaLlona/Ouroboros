import { Component, computed, input, output } from '@angular/core';
@Component({selector:'app-pagination',template:`<nav class="pagination" aria-label="Pagination"><button class="button" type="button" [disabled]="busy()||page()<=1" (click)="changed.emit(page()-1)">Previous</button><span aria-live="polite">Page {{page()}} of {{pages()}} · {{count()}} items</span><button class="button" type="button" [disabled]="busy()||page()>=pages()" (click)="changed.emit(page()+1)">Next</button></nav>`})
export class Pagination {
  readonly page=input(1);readonly count=input(0);readonly size=input(10);readonly busy=input(false);readonly changed=output<number>();
  readonly pages=computed(()=>Math.max(1,Math.ceil(this.count()/this.size())));
}

import { TestBed } from '@angular/core/testing';
import { Pagination, clampPaginationPage, paginationItems } from './pagination';

describe('Bounded numerical pagination calculation',()=>{
  it.each([
    [1,0,[]],[1,1,[1]],[1,2,[1,2]],[3,5,[1,2,3,4,5]],
    [1,100,[1,2,3,'…',99,100]],
    [15,100,[1,2,'…',13,14,15,16,17,'…',99,100]],
    [100,100,[1,2,'…',98,99,100]],
    [6,12,[1,2,3,4,5,6,7,8,'…',11,12]],
    [7,12,[1,2,'…',5,6,7,8,9,10,11,12]],
    [6,11,[1,2,3,4,5,6,7,8,9,10,11]],
  ])('calculates current=%s total=%s', (page,total,expected)=>expect(paginationItems(page as number,total as number)).toEqual(expected));
  it('normalizes invalid bounds without allocating all pages',()=>{
    for(const total of [-1,1.5,NaN,Infinity,Number.MAX_SAFE_INTEGER+1])expect(paginationItems(1,total)).toEqual([]);
    expect(paginationItems(-10,5)).toEqual([1,2,3,4,5]);expect(clampPaginationPage(20,3)).toBe(3);expect(clampPaginationPage(NaN,10)).toBe(1);
    expect(paginationItems(15,Number.MAX_SAFE_INTEGER)).toEqual([1,2,'…',13,14,15,16,17,'…',Number.MAX_SAFE_INTEGER-1,Number.MAX_SAFE_INTEGER]);
  });
  it('has sorted unique valid numbers, fills single gaps and uses ellipses only for at least two hidden pages',()=>{
    for(let total=1;total<=60;total++)for(let page=1;page<=total;page++){
      const items=paginationItems(page,total),numbers=items.filter((item):item is number=>typeof item==='number');
      expect(numbers).toEqual([...new Set(numbers)].sort((a,b)=>a-b));expect(numbers.every(number=>number>=1&&number<=total)).toBe(true);expect(numbers).toContain(page);
      expect(items.length).toBeLessThanOrEqual(13);
      items.forEach((item,index)=>{if(item==='…'){expect(typeof items[index-1]).toBe('number');expect(typeof items[index+1]).toBe('number');expect((items[index+1] as number)-(items[index-1] as number)).toBeGreaterThan(2);}else if(typeof items[index-1]==='number')expect(item-(items[index-1] as number)).toBe(1);});
    }
  });
});

describe('Shared pagination navigation and accessibility',()=>{
  it('renders the required example, current page semantics and noninteractive ellipses',async()=>{
    const fixture=TestBed.createComponent(Pagination);fixture.componentRef.setInput('page',15);fixture.componentRef.setInput('totalPages',100);await fixture.whenStable();
    const root=fixture.nativeElement as HTMLElement,changed=vi.fn();fixture.componentInstance.changed.subscribe(changed);
    expect([...root.querySelectorAll('.pagination-number')].map(button=>button.textContent)).toEqual(['1','2','13','14','15','16','17','99','100']);
    const current=root.querySelector('[aria-current=page]') as HTMLButtonElement;expect(current.textContent).toBe('15');expect(current.disabled).toBe(true);
    expect(root.querySelectorAll('.pagination-ellipsis')).toHaveLength(2);expect(root.querySelector('.pagination-ellipsis')?.hasAttribute('tabindex')).toBe(false);
    for(const button of root.querySelectorAll('button'))expect(button.type).toBe('button');
    (root.querySelector('[aria-label="Página 99"]') as HTMLButtonElement).click();expect(changed).toHaveBeenLastCalledWith(99);
    (root.querySelector('[aria-label="Página anterior"]') as HTMLButtonElement).click();expect(changed).toHaveBeenLastCalledWith(14);
    (root.querySelector('[aria-label="Página seguinte"]') as HTMLButtonElement).click();expect(changed).toHaveBeenLastCalledWith(16);
    changed.mockClear();for(const page of [15,0,-1,101,1.5,NaN,Infinity])fixture.componentInstance.request(page);current.click();expect(changed).not.toHaveBeenCalled();
  });
  it('disables boundaries/loading and hides controls for zero/one page',async()=>{
    const fixture=TestBed.createComponent(Pagination),changed=vi.fn();fixture.componentInstance.changed.subscribe(changed);fixture.componentRef.setInput('totalPages',3);await fixture.whenStable();
    const root=fixture.nativeElement as HTMLElement;expect((root.querySelector('[aria-label="Página anterior"]') as HTMLButtonElement).disabled).toBe(true);
    fixture.componentRef.setInput('page',3);await fixture.whenStable();expect((root.querySelector('[aria-label="Página seguinte"]') as HTMLButtonElement).disabled).toBe(true);
    fixture.componentRef.setInput('busy',true);await fixture.whenStable();expect([...root.querySelectorAll('button')].every(button=>button.disabled)).toBe(true);fixture.componentInstance.request(2);expect(changed).not.toHaveBeenCalled();
    for(const total of [0,1]){fixture.componentRef.setInput('totalPages',total);await fixture.whenStable();expect(root.querySelector('nav')).toBeNull();}
  });
});

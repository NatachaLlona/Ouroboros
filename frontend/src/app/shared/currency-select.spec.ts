import { TestBed } from '@angular/core/testing';
import { CurrencySelect } from './currency-select';

describe('Searchable currency selection',()=>{
  it('filters code/name without selecting search text and supports arrows, Enter and Escape',async()=>{
    const fixture=TestBed.createComponent(CurrencySelect);fixture.componentRef.setInput('fieldId','price_currency');fixture.componentRef.setInput('required',true);fixture.detectChanges();
    const component=fixture.componentInstance,root=fixture.nativeElement as HTMLElement,trigger=root.querySelector('button')!;
    expect(trigger.textContent).toContain('Selecione uma opção');trigger.click();fixture.detectChanges();await fixture.whenStable();
    const input=root.querySelector('input')!;expect(document.activeElement).toBe(input);
    expect([...root.querySelectorAll('li')].map(item=>item.textContent)).toEqual(['EUR — Euro','USD — Dólar americano','BRL — Real brasileiro']);
    expect(root.querySelector('.currency-menu button')).toBeNull();expect(root.querySelector('.currency-menu')?.textContent).not.toContain('Selecione uma opção');expect(root.querySelector('.currency-menu')?.firstElementChild).toBe(input);
    for(const text of ['uSd','DÓLAR']){input.value=text;input.dispatchEvent(new Event('input'));fixture.detectChanges();expect(root.querySelectorAll('li')).toHaveLength(1);expect(root.querySelector('li')?.textContent).toBe('USD — Dólar americano');expect(component.value()).toBe('');}
    input.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',cancelable:true}));fixture.detectChanges();expect(component.value()).toBe('');
    input.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowDown',cancelable:true}));input.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',cancelable:true}));fixture.detectChanges();expect(component.value()).toBe('USD');expect(component.open()).toBe(false);expect(trigger.textContent).toContain('USD — Dólar americano');
    trigger.click();fixture.detectChanges();await fixture.whenStable();const search=root.querySelector('input')!;search.value='no match';search.dispatchEvent(new Event('input'));fixture.detectChanges();expect(root.textContent).toContain('Nenhuma moeda encontrada');expect(component.value()).toBe('USD');search.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',cancelable:true}));fixture.detectChanges();expect(component.open()).toBe(false);expect(component.value()).toBe('USD');
  });
  it('selects plain rows with a click and closes on outside click without altering the selected code',async()=>{
    const fixture=TestBed.createComponent(CurrencySelect);fixture.componentRef.setInput('fieldId','price_currency');fixture.detectChanges();const component=fixture.componentInstance,root=fixture.nativeElement as HTMLElement;
    root.querySelector('button')!.click();fixture.detectChanges();await fixture.whenStable();(root.querySelectorAll('[role=option]')[2] as HTMLElement).click();fixture.detectChanges();expect(component.value()).toBe('BRL');expect(component.open()).toBe(false);expect(root.querySelector('button')?.textContent).toContain('BRL — Real brasileiro');
    root.querySelector('button')!.click();fixture.detectChanges();await fixture.whenStable();document.body.click();fixture.detectChanges();expect(component.open()).toBe(false);expect(component.value()).toBe('BRL');
  });
});

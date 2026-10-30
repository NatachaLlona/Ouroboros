import { TestBed } from '@angular/core/testing';
import { TierPosition } from './tier-position';
import { Api, ApiError } from '../shared/api';

describe('Complete classification order and available insertion/move positions',()=>{
  const api={request:vi.fn()};
  const item=(tier:number)=>({id_work_classifications:'WC'+String(tier).padStart(7,'0'),tier,display_name_work_classifications:'Nome '+tier,work_classification_name:'technical_'+tier});
  beforeEach(()=>{api.request.mockReset();TestBed.configureTestingModule({imports:[TierPosition],providers:[{provide:Api,useValue:api}]});});
  it('retrieves all positions, defaults to implicit append and paginates the unchanged order items',async()=>{
    api.request.mockResolvedValueOnce({count:53,page:1,page_size:50,items:Array.from({length:50},(_,i)=>item(i+1))}).mockResolvedValueOnce({count:53,page:2,page_size:50,items:[item(53),item(51),item(52)]});
    const fixture=TestBed.createComponent(TierPosition);await fixture.whenStable();fixture.detectChanges();
    expect(api.request).toHaveBeenCalledTimes(2);expect(api.request).toHaveBeenLastCalledWith('/work_classifications','GET',undefined,undefined,{page:2,page_size:50,order_by:'tier',order_direction:'asc'},false);
    const root=fixture.nativeElement as HTMLElement,trigger=root.querySelector('#tier') as HTMLButtonElement;
    expect(fixture.componentInstance.value()).toBe('');expect(trigger.textContent).toContain('Inserir na última posição (54)');expect(root.querySelectorAll('.tier-order li')).toHaveLength(10);
    const next=[...root.querySelectorAll('.pagination button')].find(button=>button.textContent==='Seguinte') as HTMLButtonElement;next.click();fixture.detectChanges();expect(root.querySelector('.tier-order li')?.textContent).toBe('Nome 11');expect(root.querySelector('.pagination')?.textContent).toContain('53 itens');
    trigger.click();fixture.detectChanges();await fixture.whenStable();expect(root.querySelectorAll('[role=option]')).toHaveLength(54);expect(root.querySelector('[role=option]')?.textContent).toBe('Inserir na última posição (54)');expect(root.querySelector('[role=listbox]')?.textContent).not.toContain('Nome');expect(root.querySelector('[role=listbox]')?.textContent).not.toContain('technical_');
    const search=root.querySelector('input[type=search]') as HTMLInputElement;search.value='53';search.dispatchEvent(new Event('input'));fixture.detectChanges();expect(root.querySelectorAll('[role=option]')).toHaveLength(1);expect(root.querySelector('[role=option]')?.textContent).toBe('53');search.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowDown',cancelable:true}));search.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',cancelable:true}));expect(fixture.componentInstance.value()).toBe('53');
    fixture.componentInstance.page.set(6);fixture.detectChanges();expect(root.querySelectorAll('.tier-order li')).toHaveLength(3);
  });
  it('preselects persisted tier in edit mode and exposes only valid move positions',async()=>{
    api.request.mockResolvedValue({count:2,page:1,page_size:50,items:[item(1),item(2)]});
    const fixture=TestBed.createComponent(TierPosition);fixture.componentRef.setInput('editing',true);fixture.componentRef.setInput('value','2');await fixture.whenStable();fixture.detectChanges();
    const trigger=fixture.nativeElement.querySelector('#tier') as HTMLButtonElement;expect(trigger.textContent.trim()).toBe('2 ⌄');expect(fixture.componentInstance.positions().map(option=>option.value)).toEqual(['1','2']);
  });
  it('does not present a partial order as complete and allows deliberate retry',async()=>{
    api.request.mockRejectedValueOnce(new ApiError(503)).mockResolvedValueOnce({count:0,page:1,page_size:50,items:[]});
    const fixture=TestBed.createComponent(TierPosition);const availability=vi.fn();fixture.componentInstance.available.subscribe(availability);await fixture.whenStable();fixture.detectChanges();
    expect(fixture.componentInstance.failure()).toContain('ordem completa');expect(fixture.nativeElement.querySelector('#tier').disabled).toBe(true);expect(availability).not.toHaveBeenCalledWith(true);
    await fixture.componentInstance.load();fixture.detectChanges();expect(fixture.componentInstance.failure()).toBe('');expect(availability).toHaveBeenLastCalledWith(true);
  });
  it('rejects changing pagination counts rather than suggesting incomplete positions',async()=>{
    api.request.mockResolvedValueOnce({count:51,page:1,page_size:50,items:Array.from({length:50},(_,i)=>item(i+1))}).mockResolvedValueOnce({count:50,page:2,page_size:50,items:[]});
    const fixture=TestBed.createComponent(TierPosition);await fixture.whenStable();expect(fixture.componentInstance.records()).toEqual([]);expect(fixture.componentInstance.failure()).not.toBe('');
  });
});

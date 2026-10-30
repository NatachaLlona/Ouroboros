import { TestBed } from '@angular/core/testing';
import { CatalogueFilters } from './filters';

describe('Compact selected-field filters',()=>{
  it('keeps Search and Clear outside the dropdown and renders only selected values',()=>{
    const fixture=TestBed.createComponent(CatalogueFilters);fixture.componentRef.setInput('resource','work_classifications');fixture.componentRef.setInput('order','tier');fixture.detectChanges();
    const component=fixture.componentInstance,search=fixture.nativeElement.querySelector('[type=submit]');expect(fixture.nativeElement.querySelector('#filter-tier')).toBeNull();expect(fixture.nativeElement.textContent).toContain('Limpar filtros');
    component.open.set(true);fixture.detectChanges();expect(fixture.nativeElement.querySelector('#filter-options input[type=checkbox]')).not.toBeNull();expect(fixture.nativeElement.querySelector('.filter-primary > .search-actions [type=submit]')).toBe(search);expect(fixture.nativeElement.querySelector('#filter-options').contains(search)).toBe(false);
    component.toggle('tier');component.set('tier','3');fixture.detectChanges();expect(fixture.nativeElement.querySelector('#filter-tier').value).toBe('3');expect(fixture.nativeElement.querySelector('#filter-created_at')).toBeNull();
    const apply=vi.fn();component.applied.subscribe(apply);component.toggle('tier');fixture.detectChanges();expect(component.filters()).not.toHaveProperty('tier');expect(fixture.nativeElement.querySelector('#filter-tier')).toBeNull();expect(apply).toHaveBeenCalledTimes(1);
    component.open.set(false);fixture.detectChanges();expect(fixture.nativeElement.textContent).toContain('Limpar filtros');
  });
});

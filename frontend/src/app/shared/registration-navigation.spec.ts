import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { CatalogueLayout } from './catalogue-layout';
import { SelectionCards } from './selection-cards';

describe('Scoped registration navigation refinements',()=>{
  beforeEach(()=>TestBed.configureTestingModule({providers:[provideRouter([])]}));
  it('only marks the home-return control for enlarged navigation styling',()=>{
    const fixture=TestBed.createComponent(CatalogueLayout);fixture.componentRef.setInput('title','Cadastrar item');fixture.componentRef.setInput('back','/cadastrar');fixture.componentRef.setInput('backLabel','Voltar a Cadastrar');fixture.detectChanges();
    const links=[...fixture.nativeElement.querySelectorAll('a')] as HTMLAnchorElement[];
    expect(links.filter(link=>link.classList.contains('home-return'))).toHaveLength(1);
    expect(links.find(link=>link.classList.contains('home-return'))!.textContent).toContain('Voltar ao início');
    expect(links.find(link=>link.textContent!.includes('Voltar a Cadastrar'))!.classList.contains('home-return')).toBe(false);
  });
  it('removes decorative badges, keeps disabled future actions, and preserves the registration route',()=>{
    const fixture=TestBed.createComponent(SelectionCards);fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.pill')).toBeNull();expect(fixture.nativeElement.textContent).not.toContain('Comece por aqui');
    expect(fixture.nativeElement.querySelectorAll('button[disabled]')).toHaveLength(2);
    expect(fixture.nativeElement.querySelector('a').getAttribute('href')).toBe('/cadastros');expect(fixture.nativeElement.querySelector('a').textContent).toContain('Cadastrar item');
    expect([...fixture.nativeElement.querySelectorAll('h2')].some((heading:any)=>heading.textContent.includes('Em breve'))).toBe(false);
  });
});

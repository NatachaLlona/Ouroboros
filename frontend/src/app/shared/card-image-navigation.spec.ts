import { TestBed } from '@angular/core/testing';
import { Router,provideRouter } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';
import { signal } from '@angular/core';
import { Home } from '../home/home';
import { Selection } from '../catalogue/selection';
import { Registration } from '../catalogue/registration';
import { Consultation } from '../catalogue/consultation';
import { SelectionCards } from './selection-cards';
import { Session } from '../auth/session';
import { Api } from './api';

describe('Card images share existing navigation and login flows',()=>{
  const session={current:signal({authenticated:false,can_create:false}),generation:signal(0),canCreate:signal(false),ensure:vi.fn(),openLogin:vi.fn(),expire:vi.fn()};
  beforeEach(()=>{vi.clearAllMocks();session.ensure.mockResolvedValue(session.current());TestBed.configureTestingModule({providers:[provideRouter([{path:'',component:Home},{path:'cadastrar',component:Selection},{path:'consultar',component:Selection,data:{consulting:true}},{path:'cadastros',component:Registration},{path:'consultas',component:Consultation}]),{provide:Session,useValue:session},{provide:Api,useValue:{request:vi.fn()}}]});});
  it.each([0,1])('home image and button %s navigate to the same intermediate destination once',async index=>{
    const harness=await RouterTestingHarness.create();
    for(const selector of ['.image-link','.card-copy .button']){
      await harness.navigateByUrl('/',Home);await harness.fixture.whenStable();const root=harness.routeNativeElement!,links=root.querySelectorAll(selector) as NodeListOf<HTMLAnchorElement>;
      expect(links[index].getAttribute('href')).toBe(index===0?'/cadastrar':'/consultar');if(selector==='.image-link')expect(links[index].getAttribute('aria-label')).toBe(index===0?'Cadastrar':'Consultar');
      links[index].click();await harness.fixture.whenStable();expect(TestBed.inject(Router).url).toBe(index===0?'/cadastrar':'/consultar');expect(session.openLogin).not.toHaveBeenCalled();
    }
  });
  it.each([false,true])('intermediate images and buttons preserve the existing protected/login flow consulting=%s',async consulting=>{
    const harness=await RouterTestingHarness.create();
    for(const selector of ['.image-link','.card-copy a']){
      await harness.navigateByUrl(consulting?'/consultar':'/cadastrar',Selection);await harness.fixture.whenStable();const root=harness.routeNativeElement!,link=root.querySelector(selector) as HTMLAnchorElement;
      expect(link.getAttribute('href')).toBe(consulting?'/consultas':'/cadastros');session.openLogin.mockClear();link.click();await harness.fixture.whenStable();expect(TestBed.inject(Router).url).toBe(consulting?'/consultas':'/cadastros');expect(session.openLogin).toHaveBeenCalledTimes(1);expect(session.openLogin.mock.calls[0][1]).toBe(consulting?'/consultas':'/cadastros');
    }
  });
  it.each([false,true])('keeps unavailable images inert and interactive elements separate consulting=%s',async consulting=>{
    const fixture=TestBed.createComponent(SelectionCards);fixture.componentRef.setInput('consulting',consulting);await fixture.whenStable();const root=fixture.nativeElement as HTMLElement;
    for(const card of [...root.querySelectorAll('article')].slice(0,2)){expect(card.querySelector('.card-image')?.tagName).toBe('DIV');expect(card.querySelector('.image-link')).toBeNull();expect(card.querySelector('a')).toBeNull();expect((card.querySelector('button') as HTMLButtonElement).disabled).toBe(true);}
    expect(root.querySelectorAll('.image-link')).toHaveLength(1);expect(root.querySelector('a a, a button, button a, button button')).toBeNull();expect(root.querySelector('.image-link')?.getAttribute('aria-label')).toBe(consulting?'Consultar itens isolados':'Cadastrar item');
  });
});

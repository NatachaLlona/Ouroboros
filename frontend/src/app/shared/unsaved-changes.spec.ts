import { Component, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';
import { Registration } from '../catalogue/registration';
import { Session } from '../auth/session';
import { Api } from './api';
import { UnsavedChanges, leaveRegistration } from './unsaved-changes';

@Component({template:'Home'}) class HomeStub {}

describe('Unsaved changes across cancel, resource changes and routing',()=>{
  const session={current:signal({authenticated:true,can_create:true,csrf_token:'test-csrf'}),canCreate:signal(true),ensure:vi.fn(),openLogin:vi.fn(),expire:vi.fn()};
  const api={request:vi.fn()};
  beforeEach(()=>{vi.clearAllMocks();session.ensure.mockResolvedValue(session.current());TestBed.configureTestingModule({imports:[Registration],providers:[provideRouter([{path:'cadastros',component:Registration,canDeactivate:[leaveRegistration]},{path:'',component:HomeStub}]),{provide:Session,useValue:session},{provide:Api,useValue:api}]});});
  async function create(){const fixture=TestBed.createComponent(Registration);await fixture.whenStable();return fixture;}
  it('uses one shared create/edit template and exact primary action labels',async()=>{
    const fixture=await create(),component=fixture.componentInstance;
    expect(fixture.nativeElement.querySelector('[type=submit]').textContent.trim()).toBe('Cadastrar');
    expect(fixture.nativeElement.querySelector('.form-actions [type=button]').textContent).toBe('Cancelar');
    await component.choose('tags');api.request.mockResolvedValueOnce({id_tags:'TG0000001',tag_name:'original',display_name_tags:'Original',description_tags:null});await component.loadRecord('TG0000001');fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[type=submit]').textContent.trim()).toBe('Salvar edição');expect(fixture.nativeElement.querySelectorAll('form')).toHaveLength(1);
  });
  it('keeps a dirty draft when resource discard is cancelled and switches only after approval',async()=>{
    const component=(await create()).componentInstance,unsaved=TestBed.inject(UnsavedChanges);component.setValue('platform_name','Draft');
    const cancelled=component.choose('tags');expect(unsaved.asking()).toBe(true);unsaved.decide(false);await cancelled;
    expect(component.selected()).toBe('platforms');expect(component.values()['platform_name']).toBe('Draft');expect(api.request).not.toHaveBeenCalled();
    const accepted=component.choose('tags');unsaved.decide(true);await accepted;expect(component.selected()).toBe('tags');expect(component.dirty()).toBe(false);expect(component.values()).not.toHaveProperty('platform_name');
  });
  it('cancel stays on the form unless discard is confirmed and never prompts for restored originals',async()=>{
    const component=(await create()).componentInstance,unsaved=TestBed.inject(UnsavedChanges),navigate=vi.spyOn(TestBed.inject(Router),'navigate').mockResolvedValue(true);
    component.setValue('platform_name','Draft');const no=component.cancelForm();unsaved.decide(false);await no;expect(navigate).not.toHaveBeenCalled();
    const yes=component.cancelForm();unsaved.decide(true);await yes;expect(navigate).toHaveBeenCalledWith(['/cadastrar'],{queryParams:undefined});expect(component.values()['platform_name']).toBe('');
    component.setValue('platform_name','Temporary');component.setValue('platform_name','');expect(await component.canDeactivate()).toBe(true);expect(unsaved.asking()).toBe(false);
  });
  it('the actual router guard preserves the page on cancel and permits confirmed departure',async()=>{
    const harness=await RouterTestingHarness.create();const component=await harness.navigateByUrl('/cadastros',Registration),unsaved=TestBed.inject(UnsavedChanges),router=TestBed.inject(Router);
    component.setValue('platform_name','Guarded');const cancelled=router.navigateByUrl('/');await vi.waitFor(()=>expect(unsaved.asking()).toBe(true));unsaved.decide(false);expect(await cancelled).toBe(false);expect(router.url).toBe('/cadastros');expect(component.values()['platform_name']).toBe('Guarded');
    const accepted=router.navigateByUrl('/');await vi.waitFor(()=>expect(unsaved.asking()).toBe(true));unsaved.decide(true);expect(await accepted).toBe(true);expect(router.url).toBe('/');
  });
  it('uses native unload prevention only while dirty and does not confirm ordinary saves',async()=>{
    const component=(await create()).componentInstance,unsaved=TestBed.inject(UnsavedChanges);const ask=vi.spyOn(unsaved,'ask');
    let event=new Event('beforeunload',{cancelable:true});component.beforeUnload(event as BeforeUnloadEvent);expect(event.defaultPrevented).toBe(false);
    await component.choose('tags');component.setValue('display_name_tags','Saved');event=new Event('beforeunload',{cancelable:true});component.beforeUnload(event as BeforeUnloadEvent);expect(event.defaultPrevented).toBe(true);
    api.request.mockResolvedValueOnce({id_tags:'TG0000001',display_name_tags:'Saved'});await component.submit(new Event('submit'));expect(ask).not.toHaveBeenCalled();expect(await component.canDeactivate()).toBe(true);
  });
});

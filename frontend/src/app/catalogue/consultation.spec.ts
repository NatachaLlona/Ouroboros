import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';
import { signal } from '@angular/core';
import { Consultation } from './consultation';
import { Session } from '../auth/session';
import { Api, ApiError } from '../shared/api';
import { Registration } from './registration';
import { leaveRegistration } from '../shared/unsaved-changes';

describe('Consultation query and confirmed deletion',()=>{
  const empty={count:0,page:1,page_size:10,items:[]};
  const session={current:signal({authenticated:true,username:'catalogue_user',can_create:true,csrf_token:'test-csrf'}),generation:signal(0),canCreate:signal(true),ensure:vi.fn(),openLogin:vi.fn(),expire:vi.fn()};
  const api={request:vi.fn()};
  beforeEach(()=>{vi.clearAllMocks();api.request.mockReset();session.current.set({authenticated:true,username:'catalogue_user',can_create:true,csrf_token:'test-csrf'});session.canCreate.set(true);session.generation.set(0);session.ensure.mockResolvedValue(session.current());api.request.mockResolvedValue(empty);TestBed.configureTestingModule({imports:[Consultation],providers:[provideRouter([]),{provide:Session,useValue:session},{provide:Api,useValue:api}]});});
  async function create(){const fixture=TestBed.createComponent(Consultation);await fixture.whenStable();return fixture.componentInstance;}
  it('requests only ten records and resets pagination for literal name and advanced tier filters',async()=>{
    const component=await create();expect(api.request).toHaveBeenLastCalledWith('/platforms','GET',undefined,undefined,expect.objectContaining({page:1,page_size:10}));
    component.choose('work_classifications');await Promise.resolve();component.name.set('50%_\\');component.apply();await Promise.resolve();
    expect(api.request).toHaveBeenLastCalledWith('/work_classifications','GET',undefined,undefined,expect.objectContaining({display_name_work_classifications:'%50\\%\\_\\\\%',order_by:'tier',page:1}));
    component.setFilter('tier','3');component.setFilter('display_name_work_classifications','%exact%');component.apply();await Promise.resolve();
    expect(api.request).toHaveBeenLastCalledWith('/work_classifications','GET',undefined,undefined,expect.objectContaining({tier:'3',display_name_work_classifications:'%exact%'}));
  });
  it('disregards an older resource response',async()=>{
    const component=await create();let resolve!:(value:unknown)=>void;
    api.request.mockReturnValueOnce(new Promise(done=>resolve=done));const old=component.load(2);
    component.choose('tags');await Promise.resolve();resolve({count:11,page:2,page_size:10,items:[{id_platforms:'PL0000001',platform_name:'Old'}]});await old;
    expect(component.selected()).toBe('tags');expect(component.items()).toEqual([]);expect(component.page()).toBe(1);
  });
  it('requires explicit confirmation, prevents duplicate DELETE and corrects an emptied last page',async()=>{
    const component=await create();component.page.set(2);component.confirmDelete({id_platforms:'PL0000001',platform_name:'Delete example'});
    expect(api.request.mock.calls.every(call=>call[1]!=='DELETE')).toBe(true);
    let resolve!:(value:unknown)=>void;api.request.mockReturnValueOnce(new Promise(done=>resolve=done)).mockResolvedValueOnce({...empty,count:10,page:2}).mockResolvedValueOnce({...empty,count:10});
    const pending=component.remove();await component.remove();expect(api.request.mock.calls.filter(call=>call[1]==='DELETE')).toHaveLength(1);
    expect(api.request).toHaveBeenLastCalledWith('/platforms/PL0000001','DELETE',undefined,'test-csrf');resolve(null);await pending;
    expect(component.pendingDelete()).toBeNull();expect(component.page()).toBe(1);expect(component.count()).toBe(10);
  });
  it('keeps dependency rejection visible without retrying DELETE',async()=>{
    const component=await create();component.confirmDelete({id_platforms:'PL0000001',platform_name:'Referenced'});api.request.mockRejectedValueOnce(new ApiError(409,'RELATIONSHIP_CONFLICT',[],'','','/platforms/PL0000001','DELETE'));
    await component.remove();expect(component.deleteError()).toContain('dependem');expect(component.pendingDelete()).not.toBeNull();expect(api.request.mock.calls.filter(call=>call[1]==='DELETE')).toHaveLength(1);
  });
  it('keeps only five successful applied searches per resource and never records failures or paging',async()=>{
    const component=await create();for(let index=0;index<7;index++){component.name.set('query '+index);component.apply();await Promise.resolve();}
    expect(component.view.recent('platforms').map(item=>item.name)).toEqual(['query 6','query 5','query 4','query 3','query 2']);
    await component.load(2);expect(component.view.recent('platforms')).toHaveLength(5);
    api.request.mockRejectedValueOnce(new ApiError(503));component.name.set('failed');component.apply();await Promise.resolve();expect(component.view.recent('platforms').some(item=>item.name==='failed')).toBe(false);
    const recent=component.view.recent('platforms')[4];component.reapply(recent);await Promise.resolve();expect(api.request).toHaveBeenLastCalledWith('/platforms','GET',undefined,undefined,expect.objectContaining({platform_name:'%query 2%',page:1,page_size:10}));
    component.choose('tags');await Promise.resolve();expect(component.view.recent('tags')).toEqual([]);expect(component.view.recent('platforms')).toHaveLength(5);
    component.view.clear('platforms');expect(component.view.recent('platforms')).toEqual([]);
  });
  it('clears criteria and edit-return context on logout or a newly signed-in session',async()=>{
    const component=await create();component.name.set('Private criteria');component.apply();await Promise.resolve();component.rememberEdit();expect(component.view.recent('platforms')).toHaveLength(1);
    session.current.update(value=>({...value,authenticated:false}));session.generation.update(value=>value+1);expect(component.view.recent('platforms')).toEqual([]);expect(component.view.context('platforms')).toBeUndefined();
    session.current.update(value=>({...value,authenticated:true}));session.generation.update(value=>value+1);expect(component.view.recent('platforms')).toEqual([]);expect(component.view.context('platforms')).toBeUndefined();
  });
  it('removes unchecked filters from subsequent queries and exposes no Cadastrar action',async()=>{
    const fixture=TestBed.createComponent(Consultation);await fixture.whenStable();const component=fixture.componentInstance;component.choose('work_classifications');await Promise.resolve();component.setFilter('tier','3');component.apply();await Promise.resolve();
    component.chosenFields.set([]);component.apply();await Promise.resolve();expect(api.request.mock.calls.at(-1)![4]).not.toHaveProperty('tier');fixture.detectChanges();expect(fixture.nativeElement.textContent).not.toContain('Cadastrar');expect(fixture.nativeElement.textContent).toContain('Limpar filtros');
  });
  it('returns from an actual edit preserving resource, page, filters, ordering and scroll',async()=>{
    TestBed.configureTestingModule({providers:[provideRouter([{path:'consultas',component:Consultation},{path:'cadastros',component:Registration,canDeactivate:[leaveRegistration]}])]});
    const record={id_tags:'TG0000001',tag_name:'original',display_name_tags:'Name',description_tags:null};
    api.request.mockImplementation((path,method,_body,_csrf,params)=>Promise.resolve(path==='/tags/TG0000001'?record:{...empty,count:path==='/tags'?12:0,page:params?.page||1,items:path==='/tags'?[record]:[]}));
    const scroll=vi.spyOn(window,'scrollTo').mockImplementation(()=>{}),descriptor=Object.getOwnPropertyDescriptor(window,'scrollY');Object.defineProperty(window,'scrollY',{configurable:true,value:345});
    try{
      const harness=await RouterTestingHarness.create(),list=await harness.navigateByUrl('/consultas',Consultation);await harness.fixture.whenStable();list.choose('tags');await harness.fixture.whenStable();list.name.set('Name');list.setFilter('tag_name','original');list.order.set('display_name_tags');list.direction.set('desc');list.apply();await harness.fixture.whenStable();await list.load(2);list.rememberEdit();
      const editor=await harness.navigateByUrl('/cadastros?resource=tags&id=TG0000001',Registration);await harness.fixture.whenStable();editor.setValue('description_tags','Edited');await editor.submit(new Event('submit'));
      const restored=await harness.navigateByUrl('/consultas',Consultation);await harness.fixture.whenStable();expect(restored.selected()).toBe('tags');expect(restored.page()).toBe(2);expect(restored.filters()['tag_name']).toBe('original');expect(restored.order()).toBe('display_name_tags');expect(restored.direction()).toBe('desc');expect(scroll).toHaveBeenCalledWith({top:345,behavior:'auto'});
      expect(api.request).toHaveBeenLastCalledWith('/tags','GET',undefined,undefined,expect.objectContaining({page:2,page_size:10,tag_name:'original',order_by:'display_name_tags',order_direction:'desc'}));
    }finally{scroll.mockRestore();if(descriptor)Object.defineProperty(window,'scrollY',descriptor);}
  });
});

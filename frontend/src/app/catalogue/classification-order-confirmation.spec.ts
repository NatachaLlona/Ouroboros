import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { signal } from '@angular/core';
import { Registration } from './registration';
import { Api, ApiError } from '../shared/api';
import { Session } from '../auth/session';
import { DESCRIPTION_MAX_LENGTH } from '../shared/description';

describe('New classification occupied-position confirmation',()=>{
  const session={current:signal({authenticated:true,can_create:true,csrf_token:'test-only'}),canCreate:signal(true),ensure:vi.fn(),openLogin:vi.fn(),expire:vi.fn()};
  const api={request:vi.fn()};
  const records=[{id_work_classifications:'WC0000001',display_name_work_classifications:'First',tier:1},{id_work_classifications:'WC0000002',display_name_work_classifications:'Second',tier:2}];
  const original=Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype,'showModal');
  beforeAll(()=>Object.defineProperty(HTMLDialogElement.prototype,'showModal',{configurable:true,value:function(this:HTMLDialogElement){this.open=true;}}));
  afterAll(()=>{if(original)Object.defineProperty(HTMLDialogElement.prototype,'showModal',original);else delete (HTMLDialogElement.prototype as any).showModal;});
  beforeEach(async()=>{
    vi.clearAllMocks();session.ensure.mockResolvedValue(session.current());
    api.request.mockImplementation(async(_path:string,method='GET')=>method==='GET'?{items:records,count:records.length,page:1,page_size:50}:{id_work_classifications:'WC0000003',display_name_work_classifications:'New classification'});
    await TestBed.configureTestingModule({imports:[Registration],providers:[provideRouter([]),{provide:Session,useValue:session},{provide:Api,useValue:api}]}).compileComponents();
  });
  function mutations(){return api.request.mock.calls.filter(call=>call[1]==='POST'||call[1]==='PUT');}
  async function setup(){
    const fixture=TestBed.createComponent(Registration),component=fixture.componentInstance;await fixture.whenStable();await component.choose('work_classifications');await fixture.whenStable();
    component.setValue('display_name_work_classifications','New classification');component.setValue('description_work_classifications','Preserved description');fixture.detectChanges();
    const root=fixture.nativeElement as HTMLElement;
    (root.querySelector('#display_name_work_classifications') as HTMLInputElement).focus();
    const trigger=root.querySelector('#tier') as HTMLButtonElement;trigger.focus();trigger.click();await fixture.whenStable();
    ([...root.querySelectorAll('#tier-options li')].find(option=>option.textContent==='1') as HTMLElement).click();await fixture.whenStable();fixture.detectChanges();
    return {fixture,component,root};
  }
  async function open(context:Awaited<ReturnType<typeof setup>>){(context.root.querySelector('button[type=submit]') as HTMLButtonElement).click();await context.fixture.whenStable();context.fixture.detectChanges();}
  it('selects without opening, then confirms only on valid submission with exact text and safe initial focus',async()=>{
    const context=await setup(),{root,component}=context;
    expect(component.values()['tier']).toBe('1');expect(component.technicalVisible()).toBe(true);expect(root.querySelector('dialog')).toBeNull();expect(mutations()).toHaveLength(0);
    await open(context);const dialog=root.querySelector('dialog')!,buttons=dialog.querySelectorAll('button');
    expect(dialog.querySelector('h2')?.textContent).toBe('🔄 Confirmar alteração da ordem');
    expect(dialog.querySelector('#order-confirmation-message')?.textContent).toBe('Você está prestes a inserir esta classificação na posição 1.A classificação que ocupava essa posição e as seguintes serão deslocadas automaticamente.Como deseja continuar?');
    expect([...dialog.querySelectorAll('strong')].map(item=>item.textContent)).toEqual(['1','A classificação que ocupava essa posição e as seguintes serão deslocadas automaticamente.']);
    expect(buttons[1].textContent).toBe('🔙 Retornar ao formulário');expect(buttons[1].classList.contains('button-primary')).toBe(true);expect(document.activeElement).toBe(buttons[1]);
    expect(buttons[2].textContent).toBe('⬇️ Inserir na última posição');expect(buttons[3].textContent).toBe('✅ Confirmar inserção');
    for(const button of [...buttons].slice(2)){expect(button.classList.contains('button-primary')).toBe(false);expect(button.type).toBe('button');}
    expect(component.pendingTechnicalName()).toBeNull();expect(root.querySelectorAll('dialog')).toHaveLength(1);expect(mutations()).toHaveLength(0);
  });
  it.each(['return','X','Escape','close'])('returns using %s without changing fields or sending POST',async mode=>{
    const context=await setup(),{root,component,fixture}=context;await open(context);const values={...component.values()},dialog=root.querySelector('dialog')!;
    if(mode==='return'||mode==='X')(dialog.querySelectorAll('button')[mode==='X'?0:1] as HTMLButtonElement).click();
    else dialog.dispatchEvent(new Event(mode==='Escape'?'cancel':'close',{cancelable:true}));
    await fixture.whenStable();expect(component.values()).toEqual(values);expect(component.pendingInsertionTier()).toBeNull();expect(mutations()).toHaveLength(0);expect(root.querySelector('dialog')).toBeNull();
    await open(context);expect(component.pendingInsertionTier()).toBe('1');expect(component.pendingTechnicalName()).toBeNull();
  });
  it.each([true,false])('submits immediately with append=%s, preserves payload, prevents duplicates and clears success',async append=>{
    const context=await setup(),{root,component,fixture}=context;await open(context);
    let resolve!:(value:unknown)=>void;api.request.mockImplementationOnce(()=>new Promise(done=>resolve=done));
    const button=root.querySelectorAll('dialog button')[append?2:3] as HTMLButtonElement;button.click();button.click();await component.submit(new Event('submit'));
    expect(mutations()).toHaveLength(1);expect(component.busy()).toBe(true);
    const body=mutations()[0][2];expect(body).toMatchObject({display_name_work_classifications:'New classification',description_work_classifications:'Preserved description',work_classification_name:'new_classification'});
    if(append){expect(body).not.toHaveProperty('tier');expect(component.values()['tier']).toBe('');}else expect(body).toHaveProperty('tier',1);
    expect(component.pendingTechnicalName()).toBeNull();expect(component.pendingInsertionTier()).toBeNull();
    resolve({id_work_classifications:'WC0000003',display_name_work_classifications:'New classification'});await fixture.whenStable();fixture.detectChanges();
    expect(component.success()?.id).toBe('WC0000003');expect(component.values()['tier']).toBe('');expect(component.values()['display_name_work_classifications']).toBe('');expect(root.querySelector('.success')).not.toBeNull();expect(root.querySelector('dialog')).toBeNull();
  });
  it.each(['name','technical','description','order unavailable','invalid tier'])('validates %s before opening any confirmation',async invalid=>{
    const context=await setup(),{component,fixture,root}=context;
    if(invalid==='name')component.setValue('display_name_work_classifications','');
    if(invalid==='technical')component.setValue('work_classification_name','Invalid name');
    if(invalid==='description')component.setValue('description_work_classifications','x'.repeat(DESCRIPTION_MAX_LENGTH+1));
    if(invalid==='order unavailable')component.tierReady.set(false);
    if(invalid==='invalid tier')component.setValue('tier','0');
    await component.submit(new Event('submit'));await fixture.whenStable();expect(Object.keys(component.errors()).length).toBeGreaterThan(0);expect(root.querySelector('dialog')).toBeNull();expect(component.pendingInsertionTier()).toBeNull();expect(component.pendingTechnicalName()).toBeNull();expect(mutations()).toHaveLength(0);
  });
  it.each([true,false])('retains current data and existing feedback after API failure with append=%s',async append=>{
    const context=await setup(),{component,fixture,root}=context;await open(context);api.request.mockRejectedValueOnce(new ApiError(422,'VALIDATION_ERROR'));
    (root.querySelectorAll('dialog button')[append?2:3] as HTMLButtonElement).click();await fixture.whenStable();fixture.detectChanges();
    expect(mutations()).toHaveLength(1);expect(component.values()).toMatchObject({tier:append?'':'1',description_work_classifications:'Preserved description',display_name_work_classifications:'New classification'});expect(component.failure()).toBeInstanceOf(ApiError);expect(root.querySelector('.form-error')).not.toBeNull();expect(component.busy()).toBe(false);expect(root.querySelector('dialog')).toBeNull();
  });
  it('revalidates after the dialog and does not chain into technical confirmation',async()=>{
    const context=await setup(),{component,root,fixture}=context;await open(context);component.setValue('work_classification_name','Invalid');
    (root.querySelectorAll('dialog button')[3] as HTMLButtonElement).click();await fixture.whenStable();expect(mutations()).toHaveLength(0);expect(component.fieldError('work_classification_name')).not.toBe('');expect(component.pendingTechnicalName()).toBeNull();expect(component.pendingInsertionTier()).toBeNull();
  });
  it('keeps automatic append, edit and other resources outside order confirmation',async()=>{
    const context=await setup(),{component}=context;component.setValue('tier','');await component.submit(new Event('submit'));expect(mutations()).toHaveLength(1);expect(mutations()[0][2]).not.toHaveProperty('tier');expect(component.pendingInsertionTier()).toBeNull();
    component.another();component.original.set({id_work_classifications:'WC0000003',display_name_work_classifications:'Original',work_classification_name:'original',tier:2});component.setValue('display_name_work_classifications','Renamed');component.setValue('work_classification_name','original');component.setValue('tier','1');await component.submit(new Event('submit'));expect(mutations().at(-1)?.[1]).toBe('PUT');expect(component.pendingInsertionTier()).toBeNull();
    component.dirty.set(false);await component.choose('tags');component.setValue('display_name_tags','Tag');await component.submit(new Event('submit'));expect(mutations().at(-1)?.[0]).toBe('/tags');expect(component.pendingInsertionTier()).toBeNull();
  });
  it('keeps name-only confirmation separate even when existing positions are occupied',async()=>{
    const {component,root,fixture}=await setup();component.another();component.setValue('display_name_work_classifications','Name only');fixture.detectChanges();
    (root.querySelector('#display_name_work_classifications') as HTMLInputElement).focus();
    const submit=root.querySelector('button[type=submit]') as HTMLButtonElement;submit.dispatchEvent(new Event('pointerdown',{bubbles:true,cancelable:true}));submit.click();await fixture.whenStable();
    expect(component.pendingTechnicalName()).toBe('name_only');expect(component.pendingInsertionTier()).toBeNull();expect(root.querySelectorAll('dialog')).toHaveLength(1);expect(mutations()).toHaveLength(0);
    (root.querySelectorAll('dialog button')[2] as HTMLButtonElement).click();await fixture.whenStable();expect(mutations()).toHaveLength(1);expect(mutations()[0][2]).not.toHaveProperty('tier');expect(component.pendingInsertionTier()).toBeNull();expect(root.querySelector('dialog')).toBeNull();
  });
});

import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { signal } from '@angular/core';
import { Registration } from './registration';
import { Session } from '../auth/session';
import { Api, ApiError } from '../shared/api';

describe('Classification quick-create technical name confirmation',()=>{
  const session={current:signal({authenticated:true,can_create:true,csrf_token:'test-only'}),canCreate:signal(true),ensure:vi.fn(),openLogin:vi.fn(),expire:vi.fn()};
  const api={request:vi.fn()};
  const original=Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype,'showModal');
  beforeAll(()=>Object.defineProperty(HTMLDialogElement.prototype,'showModal',{configurable:true,value:function(this:HTMLDialogElement){this.open=true;}}));
  afterAll(()=>{if(original)Object.defineProperty(HTMLDialogElement.prototype,'showModal',original);else delete (HTMLDialogElement.prototype as any).showModal;});
  beforeEach(async()=>{
    vi.clearAllMocks();session.ensure.mockResolvedValue(session.current());
    api.request.mockImplementation(async(_path:string,method='GET')=>method==='GET'?{items:[],count:0,page:1,page_size:50}:{id_work_classifications:'WC0000001',display_name_work_classifications:'Ficção épica'});
    await TestBed.configureTestingModule({imports:[Registration],providers:[provideRouter([]),{provide:Session,useValue:session},{provide:Api,useValue:api}]}).compileComponents();
  });
  async function setup(){const fixture=TestBed.createComponent(Registration),component=fixture.componentInstance;await fixture.whenStable();await component.choose('work_classifications');await fixture.whenStable();component.setValue('display_name_work_classifications','Ficção épica');fixture.detectChanges();return {fixture,component,root:fixture.nativeElement as HTMLElement};}
  function mutations(){return api.request.mock.calls.filter(call=>call[1]==='POST'||call[1]==='PUT');}
  async function quickClick(context:Awaited<ReturnType<typeof setup>>){
    const {root,fixture}=context,name=root.querySelector('#display_name_work_classifications') as HTMLInputElement,button=root.querySelector('button[type=submit]') as HTMLButtonElement;
    name.focus();const down=new Event('pointerdown',{bubbles:true,cancelable:true});button.dispatchEvent(down);
    // Browser default focus transfer (and blur) happens only if pointerdown was not cancelled.
    if(!down.defaultPrevented)button.focus();
    button.click();await fixture.whenStable();fixture.detectChanges();return down;
  }
  it('uses the state before submit-induced blur and Manter creates immediately only once',async()=>{
    const context=await setup(),{fixture,component,root}=context;
    const down=await quickClick(context);expect(down.defaultPrevented).toBe(true);expect(mutations()).toHaveLength(0);expect(component.pendingTechnicalName()).toBe('ficcao_epica');
    const dialog=root.querySelector('dialog')!,buttons=dialog.querySelectorAll('button');expect(dialog.textContent).toContain('Confirmar Nome Técnico');expect(dialog.querySelector('strong')?.textContent).toBe('ficcao_epica');
    expect(buttons[1].textContent).toBe('Modificar');expect(buttons[1].classList.contains('button-primary')).toBe(true);expect(document.activeElement).toBe(buttons[1]);expect(buttons[2].textContent).toBe('Manter');expect(buttons[2].classList.contains('button-primary')).toBe(false);
    let resolve!:(value:unknown)=>void;api.request.mockImplementationOnce(()=>new Promise(done=>resolve=done));
    (buttons[2] as HTMLButtonElement).click();(buttons[2] as HTMLButtonElement).click();await component.submit(new Event('submit'));
    expect(mutations()).toHaveLength(1);expect(mutations()[0][2]).toMatchObject({work_classification_name:'ficcao_epica'});expect(mutations()[0][2]).not.toHaveProperty('tier');
    resolve({id_work_classifications:'WC0000001',display_name_work_classifications:'Ficção épica'});await fixture.whenStable();expect(component.success()?.id).toBe('WC0000001');expect(component.values()['display_name_work_classifications']).toBe('');
  });
  it('Modificar reveals the real suggestion, focuses the input and retains the draft without POST',async()=>{
    const context=await setup();await quickClick(context);const {root,fixture,component}=context;
    (root.querySelectorAll('dialog button')[1] as HTMLButtonElement).click();await fixture.whenStable();fixture.detectChanges();
    const input=root.querySelector('#work_classification_name') as HTMLInputElement;expect(input.value).toBe('ficcao_epica');expect(document.activeElement).toBe(input);expect(component.values()['display_name_work_classifications']).toBe('Ficção épica');expect(mutations()).toHaveLength(0);expect(root.querySelector('dialog')).toBeNull();
    component.setValue('work_classification_name','custom_name');await component.submit(new Event('submit'));expect(mutations()[0][2]).toMatchObject({work_classification_name:'custom_name'});
  });
  it.each(['escape','close','native close'])('dismisses with %s without creation or draft loss',async mode=>{
    const context=await setup();await quickClick(context);const {root,fixture,component}=context,values={...component.values()};
    if(mode==='close')(root.querySelector('dialog button') as HTMLButtonElement).click();else root.querySelector('dialog')!.dispatchEvent(new Event(mode==='escape'?'cancel':'close',{cancelable:true}));
    await fixture.whenStable();expect(component.pendingTechnicalName()).toBeNull();expect(component.values()).toEqual(values);expect(mutations()).toHaveLength(0);
  });
  it.each(['description focus','position pointer','cleared description','revealed name','manual name'])('keeps normal creation after %s',async mode=>{
    const context=await setup(),{root,component}=context;
    if(mode==='description focus')root.querySelector('textarea')!.dispatchEvent(new FocusEvent('focusin',{bubbles:true}));
    if(mode==='position pointer')root.querySelector('app-tier-position button')!.dispatchEvent(new Event('pointerdown',{bubbles:true}));
    if(mode==='cleared description'){component.setValue('description_work_classifications','Draft');component.setValue('description_work_classifications','');}
    if(mode==='revealed name')component.completeName(false);
    if(mode==='manual name')component.setValue('work_classification_name','manual_name');
    await quickClick(context);expect(component.pendingTechnicalName()).toBeNull();expect(mutations()).toHaveLength(1);
  });
  it('preserves API errors and the approved name without automatic retries',async()=>{
    const context=await setup();await quickClick(context);const {component,fixture,root}=context;api.request.mockRejectedValueOnce(new ApiError(422,'VALIDATION_ERROR'));
    (root.querySelectorAll('dialog button')[2] as HTMLButtonElement).click();await fixture.whenStable();fixture.detectChanges();
    expect(mutations()).toHaveLength(1);expect(component.values()['display_name_work_classifications']).toBe('Ficção épica');expect(component.values()['work_classification_name']).toBe('ficcao_epica');expect(root.querySelector('.form-error')).not.toBeNull();expect(component.busy()).toBe(false);
  });
  it('preserves normal blur and complete description/position payloads without a dialog',async()=>{
    const context=await setup(),{root,component,fixture}=context;
    (root.querySelector('#display_name_work_classifications') as HTMLInputElement).focus();
    (root.querySelector('textarea') as HTMLTextAreaElement).focus();fixture.detectChanges();expect(component.technicalVisible()).toBe(true);
    component.setValue('description_work_classifications','Complete draft');component.setValue('tier','1');
    await quickClick(context);expect(component.pendingTechnicalName()).toBeNull();expect(mutations()).toHaveLength(1);expect(mutations()[0][2]).toMatchObject({description_work_classifications:'Complete draft',tier:1,work_classification_name:'ficcao_epica'});
    component.another();component.tierReady.set(true);component.setValue('display_name_work_classifications','Another classification');component.requestQuickClassification();await component.submit(new Event('submit'));expect(component.pendingTechnicalName()).toBe('another_classification');
  });
  it('reveals existing validation guidance instead of confirming an invalid generated name',async()=>{
    const {component}=await setup();component.setValue('display_name_work_classifications','🐍');component.requestQuickClassification();await component.submit(new Event('submit'));
    expect(component.pendingTechnicalName()).toBeNull();expect(component.technicalVisible()).toBe(true);expect(component.fieldError('work_classification_name')).not.toBe('');expect(mutations()).toHaveLength(0);
  });
  it('retains validation and excludes tags and classification edits',async()=>{
    const {component}=await setup();component.tierReady.set(false);component.requestQuickClassification();await component.submit(new Event('submit'));expect(component.pendingTechnicalName()).toBeNull();expect(component.fieldError('tier')).not.toBe('');expect(mutations()).toHaveLength(0);
    component.tierReady.set(true);component.original.set({id_work_classifications:'WC0000001',work_classification_name:'original',display_name_work_classifications:'Original'});component.setValue('work_classification_name','original');component.requestQuickClassification();await component.submit(new Event('submit'));expect(component.pendingTechnicalName()).toBeNull();expect(mutations()[0][1]).toBe('PUT');
    component.dirty.set(false);await component.choose('tags');component.setValue('display_name_tags','Tag');component.requestQuickClassification();await component.submit(new Event('submit'));expect(component.pendingTechnicalName()).toBeNull();expect(mutations().at(-1)?.[0]).toBe('/tags');
  });
});

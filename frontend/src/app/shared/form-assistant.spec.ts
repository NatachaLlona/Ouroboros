import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { signal } from '@angular/core';
import { Registration } from '../catalogue/registration';
import { Session } from '../auth/session';
import { Api } from './api';
import { AssistantBinding, AssistantSuggestion, FormAssistantBridge, FormConversation } from './form-assistant';
import { AssistantContext, SiteAssistant } from './site-assistant';

describe('Classification assistant form protection',()=>{
  const session={current:signal({authenticated:true,can_create:true,csrf_token:'unit-csrf'}),canCreate:signal(true),ensure:vi.fn(),openLogin:vi.fn(),expire:vi.fn()};
  const api={request:vi.fn()};
  beforeEach(()=>{
    vi.clearAllMocks();session.ensure.mockResolvedValue(session.current());api.request.mockResolvedValue({items:[],count:0,page:1,page_size:50});
    TestBed.configureTestingModule({imports:[Registration],providers:[provideRouter([]),{provide:Session,useValue:session},{provide:Api,useValue:api}]});
  });
  async function create(){const fixture=TestBed.createComponent(Registration);await fixture.whenStable();await fixture.componentInstance.choose('work_classifications');await fixture.whenStable();fixture.componentInstance.tierReady.set(true);return fixture;}
  const suggestion=(value:string):AssistantSuggestion=>({reply:'Review the form.',proposals:[{field:'display_name_work_classifications',value}],missing_fields:[]});
  it('applies to existing fields and never submits the form',async()=>{
    const component=(await create()).componentInstance,snapshot=component.classificationAssistant.snapshot();
    expect(await component.classificationAssistant.apply(suggestion('Example'),snapshot,()=>true,new AbortController().signal)).toBe(true);
    expect(component.values()['display_name_work_classifications']).toBe('Example');expect(component.dirty()).toBe(true);
    expect(api.request.mock.calls.some(call=>['POST','PUT','DELETE'].includes(call[1]))).toBe(false);
  });
  it('requires explicit confirmation before overwriting a manual value',async()=>{
    const component=(await create()).componentInstance;component.setValue('display_name_work_classifications','Manual');
    const snapshot=component.classificationAssistant.snapshot();
    const cancelled=component.classificationAssistant.apply(suggestion('Suggested'),snapshot,()=>true,new AbortController().signal);
    expect(component.pendingAssistantChange()).not.toBeNull();component.decideAssistantChange(false);expect(await cancelled).toBe(false);
    expect(component.values()['display_name_work_classifications']).toBe('Manual');
    const confirmed=component.classificationAssistant.apply(suggestion('Suggested'),snapshot,()=>true,new AbortController().signal);
    component.decideAssistantChange(true);expect(await confirmed).toBe(true);expect(component.values()['display_name_work_classifications']).toBe('Suggested');
  });
  it('protects manual changes made while the model request was in flight',async()=>{
    const component=(await create()).componentInstance,snapshot=component.classificationAssistant.snapshot();
    component.setValue('display_name_work_classifications','Typed during request');
    const pending=component.classificationAssistant.apply(suggestion('Earlier suggestion'),snapshot,()=>true,new AbortController().signal);
    expect(component.pendingAssistantChange()).not.toBeNull();component.decideAssistantChange(false);await pending;
    expect(component.values()['display_name_work_classifications']).toBe('Typed during request');
  });
  it('cancels a pending confirmation when its assistant instance closes',async()=>{
    const component=(await create()).componentInstance;component.setValue('display_name_work_classifications','Manual');
    const controller=new AbortController(),pending=component.classificationAssistant.apply(suggestion('Suggested'),component.classificationAssistant.snapshot(),()=>!controller.signal.aborted,controller.signal);
    controller.abort();expect(await pending).toBe(false);expect(component.pendingAssistantChange()).toBeNull();expect(component.values()['display_name_work_classifications']).toBe('Manual');
  });
  it('ignores a stale response and retains conversation across form tabs',async()=>{
    const component=(await create()).componentInstance,snapshot=component.classificationAssistant.snapshot();
    component.classificationConversation.history.set([{role:'user',content:'A question'}]);
    await component.choose('platforms');await component.choose('work_classifications');
    expect(component.classificationConversation.history()).toHaveLength(1);
    component.classificationConversation.reset();
    expect(await component.classificationAssistant.apply(suggestion('Stale'),snapshot,()=>component.classificationConversation.epoch===snapshot.epoch,new AbortController().signal)).toBe(false);
    expect(component.values()['display_name_work_classifications']).toBe('');
  });
});

describe('Existing assistant message box integration',()=>{
  const api={request:vi.fn()};
  const session={current:signal({authenticated:true,can_create:true,csrf_token:'unit-csrf'}),expire:vi.fn(),ensure:vi.fn()};
  beforeEach(()=>{vi.clearAllMocks();TestBed.configureTestingModule({imports:[SiteAssistant],providers:[{provide:Api,useValue:api},{provide:Session,useValue:session}]});});
  async function create(){
    const fixture=TestBed.createComponent(SiteAssistant);await fixture.whenStable();
    const element=document.createElement('form'),conversation=new FormConversation(),apply=vi.fn().mockResolvedValue(true);
    const binding:AssistantBinding={conversation,available:()=>true,snapshot:()=>({mode:'create',epoch:conversation.epoch,values:{display_name_work_classifications:'',work_classification_name:'',description_work_classifications:'',tier:''}}),apply};
    TestBed.runInInjectionContext(()=>TestBed.inject(AssistantContext).registerForm(element,{onDestroy:()=>()=>{},destroyed:false}));TestBed.inject(FormAssistantBridge).bind(element,binding);
    await fixture.whenStable();fixture.componentInstance.open.set(true);fixture.detectChanges();return {fixture,binding,apply};
  }
  it('sends the existing textbox to the classification endpoint and retains newer typed input',async()=>{
    const {fixture,binding,apply}=await create(),component=fixture.componentInstance;
    let complete!:(value:AssistantSuggestion)=>void;api.request.mockReturnValue(new Promise<AssistantSuggestion>(resolve=>complete=resolve));
    component.message.set('First message');const pending=component.send();component.message.set('Next message while waiting');
    complete({reply:'A question',proposals:[],missing_fields:[]});await pending;
    expect(api.request.mock.calls[0][0]).toBe('/browser/assistant/work-classifications');expect(api.request.mock.calls[0][3]).toBe('unit-csrf');
    expect(apply).toHaveBeenCalledOnce();expect(component.message()).toBe('Next message while waiting');expect(binding.conversation.history().map(item=>item.role)).toEqual(['user','assistant']);
  });
  it('does not apply a response delivered after the balloon closes',async()=>{
    const {fixture,apply}=await create(),component=fixture.componentInstance;
    let complete!:(value:AssistantSuggestion)=>void;api.request.mockReturnValue(new Promise<AssistantSuggestion>(resolve=>complete=resolve));
    component.message.set('First message');const pending=component.send();component.close(false);
    complete({reply:'A response',proposals:[{field:'display_name_work_classifications',value:'Late'}],missing_fields:[]});await pending;
    expect(apply).not.toHaveBeenCalled();expect(component.assistantBusy()).toBe(false);
  });
  it('scrolls only the conversation to the start of a rendered reply and preserves input focus',async()=>{
    const {fixture,binding}=await create(),root=fixture.nativeElement as HTMLElement;
    const viewport=root.querySelector('.assistant-conversation') as HTMLElement,input=root.querySelector('textarea') as HTMLTextAreaElement;
    input.focus();
    const pageScroll=vi.spyOn(window,'scrollTo').mockImplementation(()=>{});
    const rectangles=vi.spyOn(HTMLElement.prototype,'getBoundingClientRect').mockImplementation(function(this:HTMLElement){
      if(this===viewport)return new DOMRect(0,100,300,200);
      if(this.dataset['messageRole']==='assistant')return new DOMRect(0,750,280,900);
      return new DOMRect();
    });
    try{
      binding.conversation.history.set([{role:'user',content:'Long message '.repeat(300)},{role:'assistant',content:'Long reply '.repeat(300)}]);
      await fixture.whenStable();
      expect(viewport.scrollTop).toBe(650);expect(pageScroll).not.toHaveBeenCalled();expect(document.activeElement).toBe(input);
      expect(root.querySelector('[data-message-role="user"]')?.classList.contains('assistant-user-message')).toBe(true);
      expect(root.querySelector('[data-message-role="assistant"]')?.classList.contains('assistant-user-message')).toBe(false);
      viewport.scrollTop=123;
      binding.conversation.history.update(history=>[...history,{role:'user',content:'Another user message'}]);
      await fixture.whenStable();expect(viewport.scrollTop).toBe(123);
    }finally{rectangles.mockRestore();pageScroll.mockRestore();}
  });
});

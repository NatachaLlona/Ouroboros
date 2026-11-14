import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { signal } from '@angular/core';
import { Registration } from '../../../../src/app/catalogue/registration';
import { Session } from '../../../../src/app/auth/session';
import { Api } from '../../../../src/app/shared/api';
import { AssistantBinding, AssistantSuggestion, FormAssistantBridge, FormConversation, applicationReply, AssistantFieldStatus } from '../../../../src/app/shared/form-assistant';
import { AssistantContext, SiteAssistant } from '../../../../src/app/shared/site-assistant';

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

describe('Shared post-application conversation policy',()=>{
  function setup(){
    const values={display_name_work_classifications:'',work_classification_name:'',description_work_classifications:'',tier:''};
    const conversation=new FormConversation();
    let fields:AssistantFieldStatus[]=[{key:'display_name_work_classifications',label:'Display Name',required:true,valid:false},
      {key:'work_classification_name',label:'Technical Name',required:true,generated:true,valid:true},
      {key:'description_work_classifications',label:'Description',required:false,valid:true},
      {key:'tier',label:'Position',required:false,valid:true}];
    const binding:AssistantBinding={assistantId:'assistant_2',conversation,available:()=>true,snapshot:()=>({mode:'create',epoch:conversation.epoch,values:{...values}}),apply:async()=>true,fields:()=>fields};
    return {binding,values,fields,setFields:(next:AssistantFieldStatus[])=>fields=next};
  }
  it('acknowledges only values confirmed by the interface, including partial application',()=>{
    const {binding,values}=setup(),before=binding.snapshot();values.display_name_work_classifications='Example';
    const reply=applicationReply(binding,{reply:'I filled everything!',proposals:[{field:'display_name_work_classifications',value:'Example'},{field:'tier',value:3}],missing_fields:[]},before);
    expect(reply).toContain('Fields verified in the form: Display Name');expect(reply).toContain('Not applied: Position');expect(reply).not.toContain('I filled everything');
  });
  it('asks only the first invalid required field in visual order and respects conditions',()=>{
    const {binding,setFields}=setup();
    setFields([{key:'first',label:'First',required:true,valid:false},{key:'conditional',label:'Conditional',required:false,valid:false},{key:'last',label:'Last',required:true,valid:false}]);
    let reply=applicationReply(binding,{reply:'',proposals:[],missing_fields:[]},binding.snapshot());
    expect(reply).toContain('First?');expect(reply).not.toContain('Last?');expect(reply).not.toContain('Conditional?');
    setFields([{key:'first',label:'First',required:true,valid:true},{key:'last',label:'Last',required:true,valid:false}]);
    reply=applicationReply(binding,{reply:'',proposals:[],missing_fields:[]},binding.snapshot());expect(reply).toContain('Last?');expect(reply).not.toContain('First?');
  });
  it('does not spontaneously ask for technical name even if automatic generation is invalid',()=>{
    const {binding,fields}=setup();fields[0].valid=true;fields[1].valid=false;
    const reply=applicationReply(binding,{reply:'What is the Technical Name?',proposals:[],missing_fields:[]},binding.snapshot());
    expect(reply).not.toContain('Technical Name?');expect(reply).toContain('automatic suggestion');
  });
  it('offers optional fields together once, accepts defaults and stops after refusal',()=>{
    const {binding,fields}=setup();fields[0].valid=true;
    const result:AssistantSuggestion={reply:'',proposals:[],missing_fields:[]};
    expect(applicationReply(binding,result,binding.snapshot())).toContain('Description, Position');
    expect(binding.conversation.optionalStatus).toBe('offered');
    expect(applicationReply(binding,result,binding.snapshot())).not.toContain('optional fields');
    applicationReply(binding,{...result,optional_declined:true},binding.snapshot());expect(binding.conversation.optionalStatus).toBe('declined');
    expect(applicationReply(binding,result,binding.snapshot())).not.toContain('optional fields');
  });
  it('does not report a description suggestion unless it actually reached the empty field',()=>{
    const {binding,values}=setup(),before=binding.snapshot();
    const result:AssistantSuggestion={reply:'I filled',proposals:[{field:'description_work_classifications',value:'Faithful account'}],missing_fields:[]};
    expect(applicationReply(binding,result,before)).not.toContain('I suggested a description');
    values.description_work_classifications='Faithful account';expect(applicationReply(binding,result,before)).toContain('I suggested a description');
  });
  it('keeps optional conversation state isolated between forms and resets it with the draft',()=>{
    const first=setup(),second=setup();first.binding.conversation.optionalStatus='declined';
    expect(second.binding.conversation.optionalStatus).toBe('unoffered');first.binding.conversation.reset();expect(first.binding.conversation.optionalStatus).toBe('unoffered');
  });
});

describe('Existing assistant message box integration',()=>{
  const api={request:vi.fn()};
  const session={current:signal({authenticated:true,can_create:true,csrf_token:'unit-csrf'}),expire:vi.fn(),ensure:vi.fn()};
  beforeEach(()=>{vi.clearAllMocks();TestBed.configureTestingModule({imports:[SiteAssistant],providers:[{provide:Api,useValue:api},{provide:Session,useValue:session}]});});
  async function create(){
    const fixture=TestBed.createComponent(SiteAssistant);await fixture.whenStable();
    const element=document.createElement('form'),conversation=new FormConversation(),apply=vi.fn().mockResolvedValue(true);
    const binding:AssistantBinding={assistantId:'assistant_2',conversation,available:()=>true,snapshot:()=>({mode:'create',epoch:conversation.epoch,values:{display_name_work_classifications:'',work_classification_name:'',description_work_classifications:'',tier:''}}),apply};
    let unregister=()=>{};
    TestBed.runInInjectionContext(()=>TestBed.inject(AssistantContext).registerForm(element,{onDestroy:callback=>{unregister=callback;return ()=>{};},destroyed:false}));TestBed.inject(FormAssistantBridge).bind(element,binding);
    await fixture.whenStable();fixture.componentInstance.open.set(true);fixture.detectChanges();return {fixture,binding,apply,unregister};
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
  it('keeps form history isolated when switching to the disabled general assistant',async()=>{
    const {fixture,binding,apply,unregister}=await create(),component=fixture.componentInstance;
    expect(component.context.assistantId()).toBe('assistant_2');
    binding.conversation.history.set([{assistant_id:'assistant_2',role:'user',content:'Form-only context'}]);
    let complete!:(value:AssistantSuggestion)=>void;api.request.mockReturnValue(new Promise<AssistantSuggestion>(resolve=>complete=resolve));
    component.message.set('Form request');const pending=component.send();
    unregister();await fixture.whenStable();expect(component.context.assistantId()).toBe('assistant_1');
    complete({reply:'Late form reply',proposals:[],missing_fields:[]});await pending;
    expect(apply).not.toHaveBeenCalled();expect(binding.conversation.history()).toHaveLength(1);expect(component.visibleMessages()).toEqual([]);
    api.request.mockClear();component.message.set('General request');await component.send();expect(api.request).not.toHaveBeenCalled();
    expect(binding.conversation.assistantId).toBe('assistant_2');
  });
  it('confirms relative position separately, rereads it and only then applies fields',async()=>{
    const {fixture,apply}=await create(),component=fixture.componentInstance;
    api.request.mockResolvedValueOnce({reply:'Review',proposals:[],missing_fields:[],position_confirmation:{token:'owned-token',message:'Antes de Amei, na posição 3?'}})
      .mockResolvedValueOnce({reply:'Confirmed',proposals:[{field:'tier',value:3}],missing_fields:[]});
    component.message.set('Antes do primeiro amei');const pending=component.send();
    await Promise.resolve();expect(component.pendingPosition()).not.toBeNull();expect(apply).not.toHaveBeenCalled();
    component.decidePosition(true);await pending;
    expect(api.request.mock.calls[1][2].confirmation).toBe('owned-token');expect(apply).toHaveBeenCalledOnce();
    expect(apply.mock.calls[0][0].proposals).toEqual([{field:'tier',value:3}]);
  });
  it('cancelling relative position makes no confirmation request or tier application',async()=>{
    const {fixture,apply}=await create(),component=fixture.componentInstance;
    api.request.mockResolvedValue({reply:'Review',proposals:[],missing_fields:[],position_confirmation:{token:'owned-token',message:'Antes de Amei?'}});
    component.message.set('Antes do primeiro amei');const pending=component.send();
    await Promise.resolve();component.decidePosition(false);await pending;
    expect(api.request).toHaveBeenCalledOnce();expect(apply.mock.calls[0][0].proposals).toEqual([]);expect(component.pendingPosition()).toBeNull();
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

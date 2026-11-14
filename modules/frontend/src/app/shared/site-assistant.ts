import { Component, DestroyRef, Directive, ElementRef, Injectable, Injector, afterNextRender, computed, effect, inject, input, signal, viewChild } from '@angular/core';
import { AssistantBinding, AssistantMessage, AssistantSuggestion, FormAssistantBridge, applicationReply, validAssistantSuggestion } from './form-assistant';
import { assistantGreeting, frontendConfig } from '../configuration';
import { Api, ApiError, safeMessage } from './api';
import { Session } from '../auth/session';
import { AudioLevelMeter } from './audio-level-meter';
import { Confirmation } from './confirmation';
import { assistantIds } from './assistant-identity';

/** Track rendered catalogue forms independently of routes and nested modal lifetimes. */
@Injectable({providedIn:'root'})
export class AssistantContext {
  private readonly forms=signal<readonly HTMLFormElement[]>([]);
  readonly activeForm=computed(()=>this.forms().at(-1)||null);
  readonly formActive=computed(()=>this.forms().length>0);
  readonly assistantId=computed(()=>this.formActive()?assistantIds.forms:assistantIds.general);
  readonly image=computed(()=>this.formActive()?frontendConfig.assistant_2_image:frontendConfig.assistant_image);
  private presentation:HTMLElement|null=null;private home:Node|null=null;
  registerPresentation(element:HTMLElement,destroy:DestroyRef):void{
    this.presentation=element;this.home=element.parentNode;this.place();
    destroy.onDestroy(()=>{this.presentation=null;this.home=null;});
  }
  private place():void{
    const target=this.activeForm()?.closest('dialog')||this.home;
    if(this.presentation&&target&&this.presentation.parentNode!==target)target.appendChild(this.presentation);
  }
  registerForm(element:HTMLFormElement,destroy:DestroyRef):void{
    this.forms.update(forms=>[...forms,element]);this.place();
    afterNextRender(()=>this.place());
    destroy.onDestroy(()=>{this.forms.update(forms=>forms.filter(form=>form!==element));this.place();});
  }
}

@Directive({selector:'form[appAssistantForm]'})
export class AssistantForm {
  readonly assistantBinding=input<AssistantBinding|null>(null);
  constructor(){
    const element:HTMLFormElement=inject(ElementRef).nativeElement,destroy=inject(DestroyRef),bridge=inject(FormAssistantBridge);
    inject(AssistantContext).registerForm(element,destroy);
    effect(()=>bridge.bind(element,this.assistantBinding()));
    destroy.onDestroy(()=>bridge.remove(element));
  }
}

interface SpeechOptions {max_audio_bytes:number;max_duration_seconds:number;request_timeout_seconds:number;recording_chunk_ms:number;audio_bits_per_second:number;}
interface SpeechResult {text:string;language:string;complete:boolean;}

@Component({selector:'app-site-assistant',imports:[AudioLevelMeter,Confirmation],host:{'[attr.data-assistant]':"context.formActive()?'forms':'general'"},template:`
  @if(context.formActive()){
    <button #trigger class="site-assistant assistant-trigger" type="button" [attr.aria-label]="'Talk to '+assistantName" [attr.aria-expanded]="open()" [attr.aria-controls]="open()?'assistant-panel':null" (click)="toggle()"><img [src]="context.image()" alt="" draggable="false"></button>
  }@else{<img class="site-assistant" [src]="context.image()" alt="" draggable="false">}
  @if(open()&&context.formActive()){
    <section id="assistant-panel" class="assistant-panel" role="region" aria-labelledby="assistant-greeting" (keydown.escape)="$event.preventDefault();$event.stopPropagation();close(true)">
      <div class="assistant-panel-content">
        <div #conversationViewport class="assistant-conversation">
        <button class="assistant-close" type="button" aria-label="Close assistant" (click)="close(true)">×</button>
        <p id="assistant-greeting" class="assistant-greeting">{{greeting}}</p>
        <p class="assistant-help">{{bridge.active()?'Type or dictate a message to fill the form. Saving requires your confirmation.':'Type or dictate a message. Sending is local only at this stage.'}}</p>
        <div class="assistant-messages" aria-live="polite" aria-label="Assistant conversation">@for(message of visibleMessages();track $index){<p [class.assistant-user-message]="message.role==='user'" [attr.data-message-role]="message.role">{{message.role==='user'?'You: ':assistantName+': '}}{{message.content}}</p>}</div>
        </div>
        <div class="assistant-composer" [class.assistant-is-recording]="state()==='recording'">
          <textarea #messageInput id="assistant-message" aria-label="Message for the assistant" rows="2" [value]="message()" (input)="edit($event)"></textarea>
          <div class="assistant-composer-actions">
            @if(state()==='recording'){
              <button type="button" class="assistant-control" aria-label="Discard audio recording" title="Discard recording" (click)="discardRecording()">×</button>
              @if(recordingStream();as stream){<app-audio-level-meter [stream]="stream" />}
            }
            <button type="button" class="assistant-control" [disabled]="state()==='requesting'||state()==='transcribing'" [attr.aria-label]="state()==='recording'?'Finish recording and transcribe':'Start recording'" [attr.aria-pressed]="state()==='recording'" (click)="record()">{{state()==='recording'?'Finish':'🎙'}}</button>
            <button type="button" class="assistant-control assistant-send" [disabled]="!message().trim()||assistantBusy()" (click)="send()">Send</button>
          </div>
        </div>
        <div class="assistant-feedback"><p class="assistant-status" role="status">{{statusText()}}</p>
        @if(error()){<p class="field-error" role="alert">{{error()}}</p>}
        </div>
      </div>
    </section>
  }
  @if(pendingPosition();as pending){<app-confirmation title="Confirm suggested position" [name]="pending.message" action="Fill position" (cancelled)="decidePosition(false)" (confirmed)="decidePosition(true)" />}
`})
export class SiteAssistant {
  readonly context=inject(AssistantContext);
  readonly bridge=inject(FormAssistantBridge);readonly assistantBusy=signal(false);
  readonly visibleMessages=computed<AssistantMessage[]>(()=>this.context.assistantId()===assistantIds.forms?(this.bridge.active()?.conversation.history()||this.messages().map(content=>({role:'user' as const,content}))):[]);
  readonly assistantName=frontendConfig.assistant_2_name;readonly greeting=assistantGreeting(true);
  readonly open=signal(false);readonly message=signal('');readonly messages=signal<string[]>([]);readonly error=signal('');
  readonly state=signal<'idle'|'requesting'|'recording'|'transcribing'>('idle');
  readonly statusText=computed(()=>this.assistantBusy()?'A interpretar a mensagem…':({idle:'',requesting:'A preparar o microfone…',recording:'Recording. Click Finish when you are done.',transcribing:'A transcrever localmente…'})[this.state()]);
  private readonly api=inject(Api);private readonly session=inject(Session);
  private readonly injector=inject(Injector);
  private readonly trigger=viewChild<ElementRef<HTMLButtonElement>>('trigger');private readonly input=viewChild<ElementRef<HTMLTextAreaElement>>('messageInput');
  private readonly conversationViewport=viewChild<ElementRef<HTMLDivElement>>('conversationViewport');
  private recorder:MediaRecorder|null=null;private stream:MediaStream|null=null;private timer:ReturnType<typeof setTimeout>|undefined;
  readonly recordingStream=signal<MediaStream|null>(null);
  private request:AbortController|null=null;private generation=0;
  private assistantRequest:AbortController|null=null;
  constructor(){
    const host:ElementRef<HTMLElement>=inject(ElementRef),destroy=inject(DestroyRef);
    afterNextRender(()=>this.context.registerPresentation(host.nativeElement,destroy));
    let activeForm:HTMLFormElement|null=null;
    let activeBinding:AssistantBinding|null=null;
    effect(()=>{const next=this.context.activeForm(),binding=this.bridge.active();if(next!==activeForm||binding!==activeBinding){activeForm=next;activeBinding=binding;this.close(false);}});
    let previousResponse:AssistantMessage|undefined;
    effect(()=>{
      const response=[...this.visibleMessages()].reverse().find(message=>message.role==='assistant');
      if(!this.open()){previousResponse=undefined;return;}
      if(!response||response===previousResponse)return;
      previousResponse=response;
      afterNextRender(()=>{
        if(!this.open()||[...this.visibleMessages()].reverse().find(message=>message.role==='assistant')!==response)return;
        const viewport=this.conversationViewport()?.nativeElement;
        const replies=viewport?.querySelectorAll<HTMLElement>('[data-message-role="assistant"]');
        const target=replies?.item(replies.length-1);
        // Scroll only the conversation viewport; preserve page position and input focus.
        if(viewport&&target)viewport.scrollTop+=target.getBoundingClientRect().top-viewport.getBoundingClientRect().top-viewport.clientTop;
      },{injector:this.injector});
    });
    destroy.onDestroy(()=>this.close(false));
  }
  toggle():void{if(this.open())this.close(false);else{this.error.set('');this.open.set(true);afterNextRender(()=>this.input()?.nativeElement.focus(),{injector:this.injector});}}
  close(focus:boolean):void{this.generation++;this.assistantRequest?.abort();this.assistantRequest=null;this.assistantBusy.set(false);this.request?.abort();this.request=null;this.release();this.state.set('idle');this.open.set(false);this.message.set('');this.messages.set([]);this.error.set('');if(focus)this.trigger()?.nativeElement.focus();}
  edit(event:Event):void{this.message.set((event.target as HTMLTextAreaElement).value);this.resize();}
  private resize():void{const input=this.input()?.nativeElement;if(input){input.rows=2;input.rows=Math.min(7,Math.max(2,input.value.split('\n').length,Math.ceil((input.scrollHeight-58)/24)));}}
  readonly pendingPosition=signal<{message:string;resolve:(accepted:boolean)=>void}|null>(null);
  decidePosition(accepted:boolean):void{const pending=this.pendingPosition();this.pendingPosition.set(null);pending?.resolve(accepted);}
  private confirmPosition(message:string,abort:AbortSignal):Promise<boolean>{
    return new Promise(resolve=>{const cancel=()=>this.decidePosition(false);const finish=(accepted:boolean)=>{abort.removeEventListener('abort',cancel);resolve(accepted);};abort.addEventListener('abort',cancel,{once:true});this.pendingPosition.set({message,resolve:finish});if(abort.aborted)cancel();});
  }
  async send():Promise<void>{
    if(this.context.assistantId()!==assistantIds.forms)return;
    const text=this.message().trim();if(!text||this.assistantBusy())return;
    const binding=this.bridge.active();
    if(binding&&(!binding.available()||text.length>4000)){this.error.set(text.length>4000?'Send a message of up to 4000 characters.':'Wait for the form to become available.');return;}
    const snapshot=binding?.snapshot();let history=binding?.conversation.history().slice(-20)||[];
    if(snapshot){while(history.length&&new TextEncoder().encode(JSON.stringify({mode:snapshot.mode,values:snapshot.values,message:text,history})).length>120000)history=history.slice(1);}
    this.message.set('');const input=this.input()?.nativeElement;if(input){input.value='';input.rows=2;input.focus();}
    if(!binding||!snapshot){this.messages.update(messages=>[...messages.slice(-19),text]);return;}
    this.error.set('');this.assistantBusy.set(true);const controller=new AbortController();this.assistantRequest=controller;
    const current=()=>this.assistantRequest===controller&&this.open()&&this.context.assistantId()===binding.assistantId&&this.bridge.active()===binding&&binding.conversation.epoch===snapshot.epoch&&!controller.signal.aborted;
    try{
      let result=await this.api.request<AssistantSuggestion>('/browser/assistant/work-classifications','POST',{assistant_id:binding.assistantId,mode:snapshot.mode,record_id:snapshot.record_id||null,technical_visible:!!snapshot.technical_visible,optional_status:binding.conversation.optionalStatus,values:snapshot.values,message:text,history},this.session.current().csrf_token,{},true,controller.signal);
      if(!current())return;
      if(!validAssistantSuggestion(result))throw new ApiError(502);
      for(let attempt=0;result.position_confirmation&&attempt<3;attempt++){
        const confirmation=result.position_confirmation;
        if(!await this.confirmPosition(confirmation.message,controller.signal)){result={...result,position_confirmation:null,notice:'The position was not applied.',reply:''};break;}
        if(!current())return;
        const next=await this.api.request<AssistantSuggestion>('/browser/assistant/work-classifications','POST',{assistant_id:binding.assistantId,mode:snapshot.mode,record_id:snapshot.record_id||null,technical_visible:!!snapshot.technical_visible,values:snapshot.values,message:text,history,confirmation:confirmation.token},this.session.current().csrf_token,{},true,controller.signal);
        if(!current())return;
        if(!validAssistantSuggestion(next))throw new ApiError(502);
        result={...next,proposals:[...result.proposals.filter(item=>item.field!=='tier'),...next.proposals]};
      }
      if(result.position_confirmation){result={...result,proposals:result.proposals.filter(item=>item.field!=='tier'),notice:'The order keeps changing. Request the relative position again.'};}
      await binding.apply(result,snapshot,current,controller.signal);if(!current())return;
      const reply=applicationReply(binding,result,snapshot);
      const additions:AssistantMessage[]=[{assistant_id:binding.assistantId,role:'user',content:text},{assistant_id:binding.assistantId,role:'assistant',content:reply.slice(0,4000)}];
      binding.conversation.history.set([...history,...additions].slice(-20));
    }catch(error){if(current()){this.error.set(safeMessage(error));this.message.update(value=>text+(value?'\n'+value:''));await this.recover(error);}}
    finally{if(this.assistantRequest===controller){this.assistantRequest=null;this.assistantBusy.set(false);}}
  }
  private release():void{
    if(this.timer!==undefined)clearTimeout(this.timer);this.timer=undefined;
    if(this.recorder){this.recorder.ondataavailable=null;this.recorder.onstop=null;this.recorder.onerror=null;if(this.recorder.state!=='inactive')this.recorder.stop();this.recorder=null;}
    this.stream?.getTracks().forEach(track=>track.stop());this.stream=null;
    this.recordingStream.set(null);
  }
  discardRecording():void{
    if(this.state()!=='recording')return;
    this.generation++;this.request?.abort();this.request=null;this.release();this.state.set('idle');this.error.set('');
  }
  async record():Promise<void>{
    if(this.state()==='recording'){if(this.recorder?.state==='recording')this.recorder.stop();this.stream?.getTracks().forEach(track=>track.stop());return;}
    if(this.state()!=='idle')return;
    this.error.set('');
    if(!navigator.mediaDevices?.getUserMedia||typeof MediaRecorder==='undefined'){this.error.set('Recording is unavailable in this browser or connection. Use HTTPS or localhost.');return;}
    const mime=['audio/webm;codecs=opus','audio/ogg;codecs=opus','audio/mp4'].find(type=>MediaRecorder.isTypeSupported(type));
    if(!mime){this.error.set('The browser does not offer a supported audio format.');return;}
    const generation=++this.generation;this.state.set('requesting');this.request=new AbortController();
    try{
      const options=await this.api.request<SpeechOptions>('/browser/transcription/options','GET',undefined,undefined,{},true,this.request.signal);
      if(generation!==this.generation)return;
      if([options.max_audio_bytes,options.max_duration_seconds,options.request_timeout_seconds,options.recording_chunk_ms,options.audio_bits_per_second].some(value=>!Number.isSafeInteger(value)||value<1))throw new ApiError(502);
      const stream=await navigator.mediaDevices.getUserMedia({audio:true});
      if(generation!==this.generation){stream.getTracks().forEach(track=>track.stop());return;}
      this.stream=stream;const recorder=new MediaRecorder(stream,{mimeType:mime,audioBitsPerSecond:options.audio_bits_per_second});this.recorder=recorder;
      const chunks:Blob[]=[];let bytes=0;
      recorder.ondataavailable=event=>{
        if(generation!==this.generation||!event.data.size)return;
        bytes+=event.data.size;
        if(bytes>options.max_audio_bytes){this.generation++;this.release();this.state.set('idle');this.error.set('The recording exceeds the size limit. Record a shorter message.');return;}
        chunks.push(event.data);
      };
      recorder.onerror=()=>{if(generation!==this.generation)return;this.generation++;this.release();this.state.set('idle');this.error.set('Could not finish recording. Check your device.');};
      recorder.onstop=()=>{if(generation!==this.generation)return;const blob=new Blob(chunks,{type:mime});this.release();if(!blob.size){this.state.set('idle');this.error.set('The recording is empty.');return;}void this.transcribe(blob,generation,options);};
      recorder.start(options.recording_chunk_ms);this.recordingStream.set(stream);this.state.set('recording');
      this.timer=setTimeout(()=>{if(generation===this.generation&&recorder.state==='recording'){recorder.stop();stream.getTracks().forEach(track=>track.stop());}},options.max_duration_seconds*1000);
    }catch(error){if(generation!==this.generation)return;this.release();this.state.set('idle');const name=error instanceof DOMException?error.name:'';this.error.set(name==='NotAllowedError'?'Microphone permission denied. Allow access in your browser.':name==='NotFoundError'?'No microphone found.':name==='NotReadableError'?'The microphone is unavailable or in use by another application.':error instanceof ApiError?safeMessage(error):'Could not start recording in this browser.');await this.recover(error);}
  }
  private async transcribe(audio:Blob,generation:number,options:SpeechOptions):Promise<void>{
    this.state.set('transcribing');this.request=new AbortController();
    try{
      const result=await this.api.request<SpeechResult>('/browser/transcription','POST',audio,this.session.current().csrf_token,{},true,this.request.signal,options.request_timeout_seconds*1000);
      if(generation!==this.generation||!this.open())return;
      if(typeof result.text!=='string'||typeof result.language!=='string'||result.complete!==true)throw new ApiError(502);
      this.message.update(text=>text+(text&&!/\s$/.test(text)?'\n':'')+result.text);
      const input=this.input()?.nativeElement;if(input){input.value=this.message();this.resize();}
    }catch(error){if(generation===this.generation){this.error.set(safeMessage(error));await this.recover(error);}}
    finally{if(generation===this.generation){this.request=null;this.state.set('idle');}}
  }
  private async recover(error:unknown):Promise<void>{if(error instanceof ApiError&&error.status===401)this.session.expire();if(error instanceof ApiError&&error.code==='CSRF_REJECTED'){try{await this.session.ensure(true);}catch{/* Keep the editable draft; never retry audio automatically. */}}}
}

import { Component, DestroyRef, Directive, ElementRef, Injectable, Injector, afterNextRender, computed, effect, inject, input, signal, viewChild } from '@angular/core';
import { AssistantBinding, AssistantMessage, AssistantSuggestion, FormAssistantBridge, classificationFields } from './form-assistant';
import { assistantGreeting, frontendConfig } from '../frontend.config';
import { Api, ApiError, safeMessage } from './api';
import { Session } from '../auth/session';

/** Track rendered catalogue forms independently of routes and nested modal lifetimes. */
@Injectable({providedIn:'root'})
export class AssistantContext {
  private readonly forms=signal<readonly HTMLFormElement[]>([]);
  readonly activeForm=computed(()=>this.forms().at(-1)||null);
  readonly formActive=computed(()=>this.forms().length>0);
  readonly image=computed(()=>this.formActive()?'/frontend/images/assistente_2.png':'/frontend/images/assistente.png');
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

interface SpeechOptions {max_audio_bytes:number;max_duration_seconds:number;}
interface SpeechResult {text:string;language:string;}

@Component({selector:'app-site-assistant',host:{'[attr.data-assistant]':"context.formActive()?'forms':'general'"},template:`
  @if(context.formActive()){
    <button #trigger class="site-assistant assistant-trigger" type="button" [attr.aria-label]="'Conversar com '+assistantName" [attr.aria-expanded]="open()" [attr.aria-controls]="open()?'assistant-panel':null" (click)="toggle()"><img [src]="context.image()" alt="" draggable="false"></button>
  }@else{<img class="site-assistant" [src]="context.image()" alt="" draggable="false">}
  @if(open()&&context.formActive()){
    <section id="assistant-panel" class="assistant-panel" role="region" aria-labelledby="assistant-greeting" (keydown.escape)="$event.preventDefault();$event.stopPropagation();close(true)">
      <div class="assistant-panel-content">
        <div #conversationViewport class="assistant-conversation">
        <button class="assistant-close" type="button" aria-label="Fechar assistente" (click)="close(true)">×</button>
        <p id="assistant-greeting" class="assistant-greeting">{{greeting}}</p>
        <p class="assistant-help">{{bridge.active()?'Escreva ou dite uma mensagem para preencher o formulário. O cadastro depende da sua confirmação.':'Escreva ou dite uma mensagem. O envio é apenas local nesta etapa.'}}</p>
        <div class="assistant-messages" aria-live="polite" aria-label="Conversa com o assistente">@for(message of visibleMessages();track $index){<p [class.assistant-user-message]="message.role==='user'" [attr.data-message-role]="message.role">{{message.role==='user'?'Você: ':assistantName+': '}}{{message.content}}</p>}</div>
        </div>
        <div class="assistant-composer">
          <textarea #messageInput id="assistant-message" aria-label="Mensagem para o assistente" rows="2" [value]="message()" (input)="edit($event)"></textarea>
          <div class="assistant-composer-actions">
            <button type="button" class="assistant-control" [disabled]="state()==='requesting'||state()==='transcribing'" [attr.aria-label]="state()==='recording'?'Finalizar gravação':'Iniciar gravação'" [attr.aria-pressed]="state()==='recording'" (click)="record()">{{state()==='recording'?'■':'🎙'}}</button>
            <button type="button" class="assistant-control" [disabled]="!message().trim()||assistantBusy()" (click)="send()">Enviar</button>
          </div>
        </div>
        <div class="assistant-feedback"><p class="assistant-status" role="status">{{statusText()}}</p>
        @if(error()){<p class="field-error" role="alert">{{error()}}</p>}
        </div>
      </div>
    </section>
  }
`})
export class SiteAssistant {
  readonly context=inject(AssistantContext);
  readonly bridge=inject(FormAssistantBridge);readonly assistantBusy=signal(false);
  readonly visibleMessages=computed<AssistantMessage[]>(()=>this.bridge.active()?.conversation.history()||this.messages().map(content=>({role:'user' as const,content})));
  readonly assistantName=frontendConfig.nome_assistente_2;readonly greeting=assistantGreeting(true);
  readonly open=signal(false);readonly message=signal('');readonly messages=signal<string[]>([]);readonly error=signal('');
  readonly state=signal<'idle'|'requesting'|'recording'|'transcribing'>('idle');
  readonly statusText=computed(()=>this.assistantBusy()?'A interpretar a mensagem…':({idle:'',requesting:'A preparar o microfone…',recording:'A gravar. Clique em finalizar quando terminar.',transcribing:'A transcrever localmente…'})[this.state()]);
  private readonly api=inject(Api);private readonly session=inject(Session);
  private readonly injector=inject(Injector);
  private readonly trigger=viewChild<ElementRef<HTMLButtonElement>>('trigger');private readonly input=viewChild<ElementRef<HTMLTextAreaElement>>('messageInput');
  private readonly conversationViewport=viewChild<ElementRef<HTMLDivElement>>('conversationViewport');
  private recorder:MediaRecorder|null=null;private stream:MediaStream|null=null;private timer:ReturnType<typeof setTimeout>|undefined;
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
  async send():Promise<void>{
    const text=this.message().trim();if(!text||this.assistantBusy())return;
    const binding=this.bridge.active();
    if(binding&&(!binding.available()||text.length>4000)){this.error.set(text.length>4000?'Envie uma mensagem com até 4000 caracteres.':'Aguarde o formulário ficar disponível.');return;}
    const snapshot=binding?.snapshot();let history=binding?.conversation.history().slice(-20)||[];
    if(snapshot){while(history.length&&new TextEncoder().encode(JSON.stringify({mode:snapshot.mode,values:snapshot.values,message:text,history})).length>120000)history=history.slice(1);}
    this.message.set('');const input=this.input()?.nativeElement;if(input){input.value='';input.rows=2;input.focus();}
    if(!binding||!snapshot){this.messages.update(messages=>[...messages.slice(-19),text]);return;}
    this.error.set('');this.assistantBusy.set(true);const controller=new AbortController();this.assistantRequest=controller;
    const current=()=>this.assistantRequest===controller&&this.open()&&this.bridge.active()===binding&&binding.conversation.epoch===snapshot.epoch&&!controller.signal.aborted;
    try{
      const result=await this.api.request<AssistantSuggestion>('/browser/assistant/work-classifications','POST',{mode:snapshot.mode,values:snapshot.values,message:text,history},this.session.current().csrf_token,{},true,controller.signal);
      if(!current())return;
      if(typeof result.reply!=='string'||result.reply.length>4500||!Array.isArray(result.proposals)||result.proposals.length>4||result.proposals.some(item=>!classificationFields.includes(item.field)||!(item.value===null||typeof item.value==='string'||typeof item.value==='number'))||new Set(result.proposals.map(item=>item.field)).size!==result.proposals.length)throw new ApiError(502);
      const applied=await binding.apply(result,snapshot,current,controller.signal);if(!current())return;
      const reply=result.reply+(applied?'':'\nAs sugestões não foram aplicadas; os valores atuais foram preservados.');
      const additions:AssistantMessage[]=[{role:'user',content:text},{role:'assistant',content:reply.slice(0,4000)}];
      binding.conversation.history.set([...history,...additions].slice(-20));
    }catch(error){if(current()){this.error.set(safeMessage(error));this.message.update(value=>text+(value?'\n'+value:''));await this.recover(error);}}
    finally{if(this.assistantRequest===controller){this.assistantRequest=null;this.assistantBusy.set(false);}}
  }
  private release():void{
    if(this.timer!==undefined)clearTimeout(this.timer);this.timer=undefined;
    if(this.recorder){this.recorder.ondataavailable=null;this.recorder.onstop=null;this.recorder.onerror=null;if(this.recorder.state!=='inactive')this.recorder.stop();this.recorder=null;}
    this.stream?.getTracks().forEach(track=>track.stop());this.stream=null;
  }
  async record():Promise<void>{
    if(this.state()==='recording'){this.recorder?.stop();this.stream?.getTracks().forEach(track=>track.stop());return;}
    if(this.state()!=='idle')return;
    this.error.set('');
    if(!navigator.mediaDevices?.getUserMedia||typeof MediaRecorder==='undefined'){this.error.set('A gravação não é suportada neste navegador ou nesta ligação. Utilize HTTPS ou localhost.');return;}
    const mime=['audio/webm;codecs=opus','audio/ogg;codecs=opus','audio/mp4'].find(type=>MediaRecorder.isTypeSupported(type));
    if(!mime){this.error.set('O navegador não oferece um formato de áudio suportado.');return;}
    const generation=++this.generation;this.state.set('requesting');this.request=new AbortController();
    try{
      const options=await this.api.request<SpeechOptions>('/browser/transcription/options','GET',undefined,undefined,{},true,this.request.signal);
      if(generation!==this.generation)return;
      if(!Number.isSafeInteger(options.max_audio_bytes)||options.max_audio_bytes<1||!Number.isFinite(options.max_duration_seconds)||options.max_duration_seconds<1)throw new ApiError(502);
      const stream=await navigator.mediaDevices.getUserMedia({audio:true});
      if(generation!==this.generation){stream.getTracks().forEach(track=>track.stop());return;}
      this.stream=stream;const recorder=new MediaRecorder(stream,{mimeType:mime});this.recorder=recorder;
      const chunks:Blob[]=[];let bytes=0;
      recorder.ondataavailable=event=>{
        if(generation!==this.generation||!event.data.size)return;
        bytes+=event.data.size;
        if(bytes>options.max_audio_bytes){this.generation++;this.release();this.state.set('idle');this.error.set('A gravação excedeu o limite de tamanho. Grave uma mensagem mais curta.');return;}
        chunks.push(event.data);
      };
      recorder.onerror=()=>{if(generation!==this.generation)return;this.generation++;this.release();this.state.set('idle');this.error.set('Não foi possível concluir a gravação. Verifique o dispositivo.');};
      recorder.onstop=()=>{if(generation!==this.generation)return;const blob=new Blob(chunks,{type:mime});this.release();if(!blob.size){this.state.set('idle');this.error.set('A gravação está vazia.');return;}void this.transcribe(blob,generation);};
      recorder.start(250);this.state.set('recording');
      this.timer=setTimeout(()=>{if(generation===this.generation&&recorder.state==='recording'){recorder.stop();stream.getTracks().forEach(track=>track.stop());}},Math.max(250,options.max_duration_seconds*1000-500));
    }catch(error){if(generation!==this.generation)return;this.release();this.state.set('idle');const name=error instanceof DOMException?error.name:'';this.error.set(name==='NotAllowedError'?'Permissão de microfone negada. Autorize o acesso no navegador.':name==='NotFoundError'?'Nenhum microfone foi encontrado.':name==='NotReadableError'?'O microfone está indisponível ou em uso por outra aplicação.':error instanceof ApiError?safeMessage(error):'Não foi possível iniciar a gravação neste navegador.');await this.recover(error);}
  }
  private async transcribe(audio:Blob,generation:number):Promise<void>{
    this.state.set('transcribing');this.request=new AbortController();
    try{
      const result=await this.api.request<SpeechResult>('/browser/transcription','POST',audio,this.session.current().csrf_token,{},true,this.request.signal);
      if(generation!==this.generation||!this.open())return;
      if(typeof result.text!=='string'||typeof result.language!=='string')throw new ApiError(502);
      this.message.update(text=>text+(text&&!/\s$/.test(text)?'\n':'')+result.text);
      const input=this.input()?.nativeElement;if(input){input.value=this.message();this.resize();}
    }catch(error){if(generation===this.generation){this.error.set(safeMessage(error));await this.recover(error);}}
    finally{if(generation===this.generation){this.request=null;this.state.set('idle');}}
  }
  private async recover(error:unknown):Promise<void>{if(error instanceof ApiError&&error.status===401)this.session.expire();if(error instanceof ApiError&&error.code==='CSRF_REJECTED'){try{await this.session.ensure(true);}catch{/* Keep the editable draft; never retry audio automatically. */}}}
}

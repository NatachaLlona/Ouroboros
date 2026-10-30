import { Component, DestroyRef, ElementRef, HostListener, Injector, afterNextRender, computed, effect, inject, signal, untracked, viewChild } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { Session } from '../auth/session';
import { Api, ApiError, safeMessage } from '../shared/api';
import { Notice } from '../shared/notice';
import { CatalogueLayout } from '../shared/catalogue-layout';
import { ResourceTabs } from '../shared/resource-tabs';
import { SharedFormField } from '../shared/form-field';
import { FieldLabel } from '../shared/field-label';
import { descriptionError } from '../shared/description';
import { Confirmation } from '../shared/confirmation';
import { NameAutocomplete } from './autocomplete';
import { TierPosition } from './tier-position';
import { currencies, priceError } from '../shared/money';
import { UnsavedChanges } from '../shared/unsaved-changes';
import { Resource } from './models';
import { CatalogueRecord, EditorValues, resourceDefinitions, emptyValues, recordValues, editorPayload, effectiveTechnical, technicalSuggestion, technicalPattern, recordId, isResource, hasValidPrice } from './resources';

@Component({selector:'app-registration',imports:[RouterLink,Notice,CatalogueLayout,ResourceTabs,SharedFormField,Confirmation,NameAutocomplete,TierPosition,FieldLabel],template:`
  <app-catalogue-layout [platformRegistration]="selected()==='platforms'" [class.platform-registration]="selected()==='platforms'" [title]="editing() ? 'Editar '+definition().label : 'Cadastrar item'" subtitle="Uma plataforma, uma tag ou uma Classificação da Obra para o seu catálogo." [back]="editing()?'/consultas':'/cadastrar'" [backLabel]="editing()?'Voltar à consulta':'Voltar a Cadastrar'">
    <h2 id="form-choice">{{editing()?'O que deseja editar?':'O que deseja cadastrar?'}}</h2>
    <app-resource-tabs [selected]="selected()" [disabled]="busy()||loading()" (selectedChange)="choose($event)" />
    @if(loading()){<p role="status">A carregar…</p>}
    @if(notice()){<app-notice [text]="notice()" />}
    @if(editLoadFailed()){<button class="button" type="button" (click)="retryEdit()">Tentar abrir edição novamente</button>}
    @if(!loading()&&!session.canCreate()){<p class="notice" role="alert">{{session.current().authenticated?'Esta área requer permissões de catálogo: supervisor ou administrador.':'Entre para continuar. Os valores introduzidos continuam aqui.'}}</p><button class="button" type="button" (click)="session.openLogin('Entre para continuar.','/cadastros')">Entrar</button>}
    @if(success();as result){<section class="success" role="status"><span class="success-icon" aria-hidden="true">✓</span><h2>{{result.edited?'Alterações guardadas!':'Cadastro concluído!'}}</h2><p>{{result.name}}</p><p class="record-id">Identificador <strong>{{result.id}}</strong></p>
      @if(result.edited){<a class="button button-primary" routerLink="/consultas" [queryParams]="{resource:selected()}">Voltar à consulta ↗</a>}
      @else{<button class="button button-primary" type="button" (click)="another()">Cadastrar outro ↗</button>}
    </section>}
    @else{<form (submit)="submit($event)"><p class="required-note"><strong class="required-star" aria-hidden="true">*</strong> Campo obrigatório</p><fieldset [disabled]="busy()||loading()||editLoadFailed()||!session.canCreate()">
      <app-name-autocomplete [definition]="definition()" [value]="values()[definition().display]||''" (valueChange)="setValue(definition().display,$event)" [error]="fieldError(definition().display)" [enabled]="!editing()" (selected)="pendingExisting.set($event)" (completed)="completeName($event)" />
      @if(definition().technical && technicalVisible()){
        <div class="field"><app-field-label [fieldId]="definition().technical!" label="Nome técnico" [required]="editing()||!suggestion()" [help]="'Use minúsculas ASCII, números e underscores entre palavras.'+(editing()?'':' Vazio usa a sugestão válida; ao focar pode escrever um nome próprio.')" /><input #technicalInput [id]="definition().technical" [value]="values()[definition().technical!]||''" (input)="technicalChanged($event)" (focus)="technicalFocused.set(true)" (blur)="technicalFocused.set(false)" [placeholder]="technicalFocused()?'':suggestion()" [required]="editing()||!suggestion()" aria-required="true" [attr.aria-describedby]="definition().technical+'-help '+definition().technical+'-error'" [attr.aria-invalid]="fieldError(definition().technical!)?'true':null" pattern="[a-z][a-z0-9]*(_[a-z0-9]+)*">
        @if(!editing()&&!suggestion()&&!values()[definition().technical!]){<p class="field-error">Não foi possível gerar um nome técnico válido. Introduza um nome técnico.</p>}
        <p class="field-error" [id]="definition().technical+'-error'">{{fieldError(definition().technical!)}}</p></div>
      }
      @for(field of definition().fields;track field.key){
        @if(field.key==='tier'){<app-tier-position [editing]="editing()" [value]="values()['tier']||''" (valueChange)="setValue('tier',$event)" [error]="fieldError('tier')" (available)="tierReady.set($event)" />}
        @else if((field.key!=='platform_url'||values()['platform_access_types']==='website')&&(field.key!=='price_amount'||values()['platform_is_paid']==='true')&&(field.key!=='price_currency'||hasPrice())){<app-form-field [definition]="field" [requiredOverride]="field.key==='price_currency'&&hasPrice()" [value]="values()[field.key]||''" (valueChange)="setValue(field.key,$event)" [error]="fieldError(field.key)" />}
      }
      @if(failure()){<p class="form-error" role="alert">{{errorMessage()}}</p>}
      <div class="dialog-actions form-actions"><button class="button" type="button" [disabled]="busy()" (click)="cancelForm()">Cancelar</button><button class="button button-primary" [attr.aria-busy]="busy()" type="submit">{{busy()?'Salvando…':editing()?'Salvar edição':'Cadastrar'}}</button></div>
    </fieldset></form>}
  </app-catalogue-layout>
  @if(pendingExisting();as item){<app-confirmation [title]="'Esta '+definition().noun+' já existe. Gostaria de editar?'" [name]="item[definition().display]+''" action="Editar" [busy]="busy()" [error]="confirmationError()" (cancelled)="pendingExisting.set(null);confirmationError.set('')" (confirmed)="confirmExisting()" />}
`})
export class Registration {
  readonly session=inject(Session);private readonly api=inject(Api);private readonly route=inject(ActivatedRoute);private readonly injector=inject(Injector);
  private readonly router=inject(Router);private readonly unsaved=inject(UnsavedChanges);
  readonly selected=signal<Resource>('platforms');readonly definition=computed(()=>resourceDefinitions[this.selected()]);
  readonly values=signal<EditorValues>(emptyValues(resourceDefinitions.platforms));private readonly drafts=new Map<Resource,EditorValues>();
  readonly hasPrice=computed(()=>hasValidPrice(this.values()));
  readonly original=signal<CatalogueRecord|null>(null);readonly editing=computed(()=>this.original()!==null);
  readonly technicalVisible=signal(false);readonly technicalFocused=signal(false);readonly suggestion=computed(()=>this.editing()?'':technicalSuggestion(this.values()[this.definition().display]||''));
  readonly loading=signal(true);readonly busy=signal(false);readonly dirty=signal(false);readonly notice=signal('');readonly failure=signal<unknown>(null);readonly errors=signal<Record<string,string>>({});readonly errorMessage=computed(()=>safeMessage(this.failure()));
  readonly pendingExisting=signal<CatalogueRecord|null>(null);readonly confirmationError=signal('');
  readonly success=signal<{id:string;name:string;edited:boolean}|null>(null);private readonly technicalInput=viewChild<ElementRef<HTMLInputElement>>('technicalInput');
  readonly editLoadFailed=signal(false);private readonly pendingEdit=signal<string|null>(null);
  readonly tierReady=signal(false);
  constructor(){inject(DestroyRef).onDestroy(this.unsaved.register(()=>this.canDeactivate()));effect(()=>{const id=this.pendingEdit();if(id&&this.session.canCreate()&&!this.loading())untracked(()=>{this.pendingEdit.set(null);void this.openEdit(id);});});void this.initialize();}
  private async initialize():Promise<void>{
    const resource=this.route.snapshot.queryParamMap.get('resource'),id=this.route.snapshot.queryParamMap.get('id');
    if(isResource(resource))this.choose(resource);
    try{const state=await this.session.ensure();if(!state.authenticated)this.session.openLogin('Entre para continuar.','/cadastros');else if(state.can_create&&id)await this.loadRecord(id);}
    catch(error){this.notice.set(safeMessage(error));if(id)this.editLoadFailed.set(true);}finally{this.loading.set(false);if(id&&!this.original()&&!this.editLoadFailed())this.pendingEdit.set(id);}
  }
  private async openEdit(id:string):Promise<void>{this.loading.set(true);this.editLoadFailed.set(false);try{await this.loadRecord(id);}catch(error){this.editLoadFailed.set(true);this.notice.set(safeMessage(error));await this.recover(error);}finally{this.loading.set(false);}}
  retryEdit():void{const id=this.route.snapshot.queryParamMap.get('id');if(id)this.pendingEdit.set(id);}
  @HostListener('window:beforeunload',['$event']) beforeUnload(event:BeforeUnloadEvent):void{if(this.dirty()){event.preventDefault();event.returnValue='';}}
  setValue(key:string,value:string):void{this.values.update(values=>({...values,[key]:value}));const baseline=this.original()?recordValues(this.definition(),this.original()!):emptyValues(this.definition());this.dirty.set(Object.keys(baseline).some(field=>this.values()[field]!==baseline[field]));if(!this.editing())this.drafts.set(this.selected(),{...this.values()});this.errors.update(errors=>({...errors,[key]:''}));}
  technicalChanged(event:Event):void{this.setValue(this.definition().technical!,(event.target as HTMLInputElement).value);}
  completeName(focus:boolean):void{if(!this.definition().technical||!this.values()[this.definition().display]?.trim())return;this.technicalVisible.set(true);if(focus)afterNextRender(()=>this.technicalInput()?.nativeElement.focus(),{injector:this.injector});}
  async canDeactivate():Promise<boolean>{if(this.busy())return false;if(!this.dirty()||this.success())return true;const discard=await this.unsaved.ask();if(discard){this.drafts.clear();this.values.set(this.original()?recordValues(this.definition(),this.original()!):emptyValues(this.definition()));this.errors.set({});this.failure.set(null);this.technicalVisible.set(this.editing());this.dirty.set(false);}return discard;}
  async cancelForm():Promise<void>{if(!await this.canDeactivate())return;await this.router.navigate([this.editing()?'/consultas':'/cadastrar'],{queryParams:this.editing()?{resource:this.selected()}:undefined});}
  async choose(resource:Resource):Promise<void>{if(resource===this.selected()||this.busy())return;if(this.dirty()&&!await this.canDeactivate())return;this.pendingEdit.set(null);this.editLoadFailed.set(false);this.selected.set(resource);this.original.set(null);this.values.set(emptyValues(resourceDefinitions[resource]));this.technicalVisible.set(false);this.technicalFocused.set(false);this.success.set(null);this.failure.set(null);this.errors.set({});this.notice.set('');this.dirty.set(false);}
  another():void{this.values.set(emptyValues(this.definition()));this.drafts.delete(this.selected());this.dirty.set(false);this.success.set(null);this.failure.set(null);this.errors.set({});this.technicalVisible.set(false);}
  fieldError(key:string):string{return this.errors()[key]||(this.failure() instanceof ApiError&&(this.failure() as ApiError).details.some(detail=>detail.loc?.includes(key))?'Reveja este campo de acordo com a indicação acima.':'');}
  async loadRecord(id:string):Promise<void>{
    const resource=this.selected();const record=await this.api.request<CatalogueRecord>('/'+resource+'/'+encodeURIComponent(id));
    if(resource!==this.selected())return;this.original.set(record);this.values.set(recordValues(this.definition(),record));this.technicalVisible.set(!!this.definition().technical);this.dirty.set(false);this.failure.set(null);this.errors.set({});this.success.set(null);
  }
  async confirmExisting():Promise<void>{
    if(this.busy()||!this.pendingExisting())return;this.busy.set(true);this.confirmationError.set('');
    try{await this.loadRecord(recordId(this.selected(),this.pendingExisting()!));this.pendingExisting.set(null);}
    catch(error){this.confirmationError.set(safeMessage(error));await this.recover(error);}finally{this.busy.set(false);}
  }
  private async recover(error:unknown):Promise<void>{if(error instanceof ApiError&&error.status===401)this.session.expire();if(error instanceof ApiError&&error.code==='CSRF_REJECTED'){try{await this.session.ensure(true);}catch{/* Preserve the draft and original error; never retry a mutation. */}}}
  async submit(event:Event):Promise<void>{
    event.preventDefault();if(this.busy()||this.loading()||this.editLoadFailed()||this.success())return;
    if(!this.session.current().authenticated){this.session.openLogin('Entre novamente; os valores continuam aqui.','/cadastros');return;}
    if(!this.session.canCreate()){this.notice.set('Esta área requer permissões de catálogo: supervisor ou administrador.');return;}
    const definition=this.definition(),values=this.values(),errors:Record<string,string>={};
    if(!values[definition.display]?.trim())errors[definition.display]='Introduza um nome fantasia.';
    for(const field of definition.fields){
      if(field.kind==='access'&&field.required&&!values[field.key])errors[field.key]='Selecione uma opção.';
      if(field.kind==='decimal'&&values['platform_is_paid']==='true'&&priceError(values[field.key]||''))errors[field.key]=priceError(values[field.key]||'');
      if(field.key.startsWith('description_')&&(!this.original()||values[field.key]!==recordValues(definition,this.original()!)[field.key])){const error=descriptionError(values[field.key]||'');if(error)errors[field.key]=error;}
    }
    if(this.selected()==='platforms'&&this.hasPrice()&&!currencies.some(choice=>choice.code===values['price_currency'])&&!(this.editing()&&values['price_currency']===this.original()?.['price_currency']&&!!values['price_currency']))errors['price_currency']='Selecione uma opção.';
    if(this.selected()==='work_classifications'&&!this.tierReady())errors['tier']='Aguarde a ordem completa ou escolha Atualizar ordem antes de guardar.';
    if(definition.technical&&!technicalPattern.test(effectiveTechnical(definition,values,this.editing()))){errors[definition.technical]='Introduza um nome técnico válido: minúsculas ASCII e underscores entre palavras.';this.technicalVisible.set(true);}
    if(values['tier']&&(!/^[1-9][0-9]*$/.test(values['tier'])||!Number.isSafeInteger(Number(values['tier']))))errors['tier']='Use uma posição inteira positiva.';
    this.errors.set(errors);if(Object.keys(errors).length)return;
    const body=editorPayload(definition,values,this.original()||undefined);
    if(this.editing()&&!Object.keys(body).length){this.notice.set('Não há alterações para guardar.');return;}
    this.busy.set(true);this.failure.set(null);this.notice.set('');
    try{
      const edited=this.editing(),path='/'+this.selected()+(edited?'/'+recordId(this.selected(),this.original()!):'');
      const record=await this.api.request<CatalogueRecord>(path,edited?'PUT':'POST',body,this.session.current().csrf_token);
      const id=recordId(this.selected(),record),name=record[definition.display];if(!id||typeof name!=='string')throw new ApiError(502);
      this.success.set({id,name,edited});this.dirty.set(false);
      if(!edited){this.values.set(emptyValues(definition));this.drafts.delete(this.selected());this.errors.set({});this.technicalVisible.set(false);this.technicalFocused.set(false);}
      else this.original.set(record);
    }catch(error){this.failure.set(error);await this.recover(error);}finally{this.busy.set(false);}
  }
}

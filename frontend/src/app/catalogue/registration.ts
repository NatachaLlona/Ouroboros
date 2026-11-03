import { Component, DestroyRef, ElementRef, HostListener, Injector, afterNextRender, computed, effect, inject, input, signal, untracked, viewChild } from '@angular/core';
import { NgComponentOutlet, NgTemplateOutlet } from '@angular/common';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { Session } from '../auth/session';
import { Api, ApiError, safeMessage } from '../shared/api';
import { Notice } from '../shared/notice';
import { CatalogueLayout } from '../shared/catalogue-layout';
import { RegistrationNavigation } from '../shared/registration-navigation';
import { SharedFormField } from '../shared/form-field';
import { FieldLabel } from '../shared/field-label';
import { descriptionError } from '../shared/description';
import { Confirmation } from '../shared/confirmation';
import { NameAutocomplete } from './autocomplete';
import { TierPosition } from './tier-position';
import { TagCategoryField } from './tag-category-field';
import { TagCategoryRegistration } from './tag-category-registration';
import { RegistrationDrafts } from './registration-drafts';
import { TagCategoryOwner, tagCategoryAssociations } from './tag-category-association';
import { uniqueSelectValues } from '../shared/select-options';
import { currencies, priceError } from '../shared/money';
import { UnsavedChanges } from '../shared/unsaved-changes';
import { RegistrationResource as Resource } from './models';
import { CatalogueRecord, EditorValues, registrationDefinitions as resourceDefinitions, registrationTitles, emptyValues, recordValues, editorPayload, effectiveTechnical, technicalSuggestion, technicalPattern, recordId, isRegistrationResource as isResource, hasValidPrice } from './resources';

interface EmbeddedAssociation {
  resource:TagCategoryOwner;parentId:string;parentName:string;
  ready:(form:Registration)=>void;
  completed:(record:CatalogueRecord,selected:boolean)=>void;
  cancelled:()=>void;
}
const pendingAssociationValue='pending-association-draft';

@Component({selector:'app-registration',providers:[TagCategoryRegistration,RegistrationDrafts],imports:[NgComponentOutlet,NgTemplateOutlet,RouterLink,Notice,CatalogueLayout,RegistrationNavigation,SharedFormField,Confirmation,NameAutocomplete,TierPosition,FieldLabel,TagCategoryField],template:`
  <ng-template #registrationContent>
    @if(!embedded()){
    <h2 id="form-choice">{{editing()?'O que deseja editar?':'O que deseja cadastrar?'}}</h2>
    <app-registration-navigation [selected]="selected()" [disabled]="busy()||loading()" (selectedChange)="choose($event)" />
    @if(!editing()&&!success()){<div class="draft-actions"><button class="text-button" type="button" [disabled]="busy()||loading()" (click)="clearCurrentDraft()">Limpar todos os campos</button></div>}
    }
    @if(loading()){<p role="status">A carregar…</p>}
    @if(notice()){<app-notice [text]="notice()" />}
    @if(editLoadFailed()){<button class="button" type="button" (click)="retryEdit()">Tentar abrir edição novamente</button>}
    @if(!loading()&&!session.canCreate()){<p class="notice" role="alert">{{session.current().authenticated?'Esta área requer permissões de catálogo: supervisor ou administrador.':'Entre para continuar. Os valores introduzidos continuam aqui.'}}</p><button class="button" type="button" (click)="session.openLogin('Entre para continuar.','/cadastros')">Entrar</button>}
    @if(success();as result){<section class="success" role="status"><span class="success-icon" aria-hidden="true">✓</span><h2>{{result.edited?'Alterações guardadas!':'Cadastro concluído!'}}</h2><p>{{result.name}}</p><p class="record-id">Identificador <strong>{{result.id}}</strong></p>
      @if(result.edited){<a class="button button-primary" routerLink="/consultas" [queryParams]="{resource:selected()}">Voltar à consulta ↗</a>}
      @else{<button class="button button-primary" type="button" (click)="another()">Cadastrar outro ↗</button>}
    </section>}
    @else{<form (submit)="$event.stopPropagation();submit($event)"><p class="required-note"><strong class="required-star" aria-hidden="true">*</strong> Campo obrigatório</p><fieldset [disabled]="busy()||loading()||editLoadFailed()||!session.canCreate()">
      <app-name-autocomplete [definition]="definition()" [value]="values()[definition().display]||''" (valueChange)="setValue(definition().display,$event)" [error]="fieldError(definition().display)" [enabled]="!editing()&&selected()!=='tag_categories'&&!tagCategories.pending()" (selected)="pendingExisting.set($event)" (completed)="completeName($event)" />
      @if(definition().technical && technicalVisible()){
        <div class="field"><app-field-label [fieldId]="definition().technical!" label="Nome técnico" [required]="editing()||!suggestion()" [help]="'Use minúsculas ASCII, números e underscores entre palavras.'+(editing()?'':' Vazio usa a sugestão válida; ao focar pode escrever um nome próprio.')" /><input #technicalInput [id]="definition().technical" [value]="values()[definition().technical!]||''" (input)="technicalChanged($event)" (focus)="technicalFocused.set(true)" (blur)="technicalFocused.set(false)" [placeholder]="technicalFocused()?'':suggestion()" [required]="editing()||!suggestion()" aria-required="true" [attr.aria-describedby]="definition().technical+'-help '+definition().technical+'-error'" [attr.aria-invalid]="fieldError(definition().technical!)?'true':null" pattern="[a-z][a-z0-9]*(_[a-z0-9]+)*">
        @if(!editing()&&!suggestion()&&!values()[definition().technical!]){<p class="field-error">Não foi possível gerar um nome técnico válido. Introduza um nome técnico.</p>}
        <p class="field-error" [id]="definition().technical+'-error'">{{fieldError(definition().technical!)}}</p></div>
      }
      @for(field of definition().fields;track field.key){
        @if(field.key==='tier'){<app-tier-position [editing]="editing()" [value]="values()['tier']||''" (valueChange)="setValue('tier',$event)" [error]="fieldError('tier')" (available)="tierReady.set($event)" />}
        @else if((field.key!=='platform_url'||values()['platform_access_types']==='website')&&(field.key!=='price_amount'||values()['platform_is_paid']==='true')&&(field.key!=='price_currency'||hasPrice())){<app-form-field [definition]="field" [requiredOverride]="field.key==='price_currency'&&hasPrice()" [value]="values()[field.key]||''" (valueChange)="setValue(field.key,$event)" [error]="fieldError(field.key)" />}
      }
      @if(selected()==='tags'||selected()==='tag_categories'){
        <app-tag-category-field [owner]="association().owner" [value]="associationIds()" (valueChange)="setAssociationIds($event)" [error]="fieldError(association().relatedKey)" [disabled]="busy()||tagCategories.uncertain()" [allowCreate]="!embedded()&&!editing()" (createRequested)="openRelatedRegistration()" [extraChoices]="relatedChoices()" [refresh]="associationRefresh()" />
        @if(embedded()&&!embedded()!.parentId){<p class="help">{{pendingAssociationMessage()}}</p>}
        @if(editing()&&tagCategories.pending()&&!busy()){<p class="notice" role="status">Algumas alterações podem já ter sido guardadas. As seleções foram preservadas; tente Salvar edição novamente para concluir os vínculos. Sair não desfaz alterações já gravadas.</p>}
        @if(selected()==='tags'){
          @if(tagCategories.created()){<p class="notice" role="status">A Tag já foi criada. Conclua as categorias com Cadastrar; uma nova tentativa reutiliza a mesma Tag. Se sair, os dados já gravados permanecem.</p>}
          @if(tagCategories.uncertain()){<p class="form-error" role="alert">Não foi possível confirmar a criação da Tag. Verifique o cadastro em Consultar antes de iniciar outra tentativa; o envio não será repetido automaticamente.</p>}
        }@else{
          @if(tagCategories.created()){<p class="notice" role="status">A Categoria de Tag já foi criada. Conclua os vínculos com Cadastrar; uma nova tentativa reutiliza a mesma categoria. Se sair, os dados já gravados permanecem.</p>}
          @if(tagCategories.uncertain()){<p class="form-error" role="alert">Não foi possível confirmar a criação da categoria. Verifique se ela foi criada antes de iniciar outra tentativa; o envio não será repetido automaticamente.</p>}
        }
      }
      @if(failure()){<p class="form-error" role="alert">{{errorMessage()}}</p>}
      <div class="dialog-actions form-actions"><button class="button" type="button" [disabled]="busy()" (click)="cancelForm()">Cancelar</button><button class="button button-primary" [attr.aria-busy]="busy()" type="submit">{{busy()?'Salvando…':editing()?'Salvar edição':'Cadastrar'}}</button></div>
    </fieldset></form>}
  </ng-template>
  @if(embedded()){
    <ng-container [ngTemplateOutlet]="registrationContent" />
  }@else{
    <app-catalogue-layout [singleBackLink]="!editing()||selected()==='platforms'" [class.platform-registration]="selected()==='platforms'" [title]="title()" subtitle="Uma plataforma, uma tag ou uma Classificação da Obra para o seu catálogo." [back]="editing()?'/consultas':'/cadastrar'" [backLabel]="editing()?'Voltar à consulta':'Voltar a Cadastrar'">
      <ng-container [ngTemplateOutlet]="registrationContent" />
    </app-catalogue-layout>
  }
  @if(associationContext();as context){
    <dialog #associationDialog class="modal category-create-modal" aria-labelledby="association-modal-title" (cancel)="$event.preventDefault();closeRelatedRegistration()">
      <div class="modal-content"><div class="modal-top"><h2 id="association-modal-title">{{registrationTitles[context.resource]}}</h2><button class="icon-button" type="button" [attr.aria-label]="'Fechar cadastro de '+resourceDefinitions[context.resource].noun" [disabled]="associationBusy()" (click)="closeRelatedRegistration()">×</button></div>
        <ng-container *ngComponentOutlet="registrationComponent;inputs:{embedded:context}" />
      </div>
    </dialog>
  }
  @if(pendingExisting();as item){<app-confirmation [title]="'Esta '+definition().noun+' já existe. Gostaria de editar?'" [name]="item[definition().display]+''" action="Editar" [busy]="busy()" [error]="confirmationError()" (cancelled)="pendingExisting.set(null);confirmationError.set('')" (confirmed)="confirmExisting()" />}
`})
export class Registration {
  readonly registrationTitles=registrationTitles;readonly resourceDefinitions=resourceDefinitions;
  readonly embedded=input<EmbeddedAssociation|null>(null);
  readonly registrationComponent=Registration;
  readonly associationContext=signal<EmbeddedAssociation|null>(null);readonly associationRefresh=signal(0);
  private readonly associationForm=signal<Registration|null>(null);private associationReturnFocus:HTMLElement|null=null;
  private readonly createdRelatedChoices=signal<Partial<Record<TagCategoryOwner,{value:string;label:string}[]>>>({});
  private readonly associationDialog=viewChild<ElementRef<HTMLDialogElement>>('associationDialog');
  readonly associationBusy=computed(()=>!!this.associationContext()&&!!this.associationForm()?.busy());
  readonly relatedChoices=computed(()=>{const context=this.embedded();return context?[{value:context.parentId||pendingAssociationValue,label:context.parentName}]:this.createdRelatedChoices()[this.association().related]||[];});
  readonly pendingAssociationMessage=computed(()=>this.embedded()?.resource==='tags'?'A Categoria de Tag em cadastro ainda não foi salva. Seu vínculo será criado somente ao cadastrar a categoria.':'A Tag em cadastro ainda não foi salva. Seu vínculo será criado somente ao cadastrar a Tag.');
  readonly session=inject(Session);private readonly api=inject(Api);private readonly route=inject(ActivatedRoute);private readonly injector=inject(Injector);
  private readonly router=inject(Router);private readonly unsaved=inject(UnsavedChanges);
  readonly selected=signal<Resource>('platforms');readonly definition=computed(()=>resourceDefinitions[this.selected()]);
  readonly title=computed(()=>this.editing()?'Editar '+this.definition().label:registrationTitles[this.selected()]);
  readonly values=signal<EditorValues>(emptyValues(resourceDefinitions.platforms));private readonly drafts=inject(RegistrationDrafts);
  readonly hasDraftChanges=computed(()=>this.dirty()||this.drafts.hasChanges());
  readonly hasPrice=computed(()=>hasValidPrice(this.values()));
  readonly original=signal<CatalogueRecord|null>(null);readonly editing=computed(()=>this.original()!==null);
  readonly technicalVisible=signal(false);readonly technicalFocused=signal(false);readonly suggestion=computed(()=>this.editing()?'':technicalSuggestion(this.values()[this.definition().display]||''));
  readonly loading=signal(true);readonly busy=signal(false);readonly dirty=signal(false);readonly notice=signal('');readonly failure=signal<unknown>(null);readonly errors=signal<Record<string,string>>({});readonly errorMessage=computed(()=>safeMessage(this.failure()));
  readonly pendingExisting=signal<CatalogueRecord|null>(null);readonly confirmationError=signal('');
  readonly success=signal<{id:string;name:string;edited:boolean}|null>(null);private readonly technicalInput=viewChild<ElementRef<HTMLInputElement>>('technicalInput');
  readonly editLoadFailed=signal(false);private readonly pendingEdit=signal<string|null>(null);private editGeneration=0;
  readonly tierReady=signal(false);
  readonly categoryIds=signal<string[]>([]);readonly tagIds=signal<string[]>([]);readonly tagCategories=inject(TagCategoryRegistration);
  readonly association=computed(()=>tagCategoryAssociations[this.selected()==='tag_categories'?'tag_categories':'tags']);
  readonly associationIds=computed(()=>this.selected()==='tag_categories'?this.tagIds():this.categoryIds());
  readonly originalAssociationIds=signal<string[]>([]);
  readonly associationChanged=computed(()=>{const original=new Set(this.originalAssociationIds()),selected=this.associationIds();return selected.length!==original.size||selected.some(id=>!original.has(id));});
  private resetTagCategories():void{this.categoryIds.set([]);this.tagIds.set([]);this.originalAssociationIds.set([]);this.tagCategories.reset();}
  private storeCurrentDraft():void{
    if(this.editing())return;
    this.drafts.save(this.selected(),{values:{...this.values()},categoryIds:[...this.categoryIds()],tagIds:[...this.tagIds()],originalAssociationIds:[...this.originalAssociationIds()],technicalVisible:this.technicalVisible(),dirty:this.dirty(),errors:{...this.errors()},failure:this.failure(),notice:this.notice(),receipt:this.tagCategories.snapshot()});
  }
  private restoreCurrentDraft():void{
    const draft=this.drafts.get(this.selected());this.drafts.remove(this.selected());
    this.values.set(draft?{...draft.values}:emptyValues(this.definition()));
    this.categoryIds.set(draft?[...draft.categoryIds]:[]);this.tagIds.set(draft?[...draft.tagIds]:[]);this.originalAssociationIds.set(draft?[...draft.originalAssociationIds]:[]);
    this.tagCategories.restore(draft?.receipt);this.technicalVisible.set(draft?.technicalVisible||false);this.technicalFocused.set(false);
    this.errors.set(draft?{...draft.errors}:{});this.failure.set(draft?.failure??null);this.notice.set(draft?.notice||'');this.dirty.set(draft?.dirty||false);
    this.success.set(null);this.pendingExisting.set(null);this.confirmationError.set('');this.tierReady.set(false);
  }
  private resetCurrentDraft():void{
    this.drafts.remove(this.selected());this.resetTagCategories();this.values.set(emptyValues(this.definition()));
    this.errors.set({});this.failure.set(null);this.notice.set('');this.success.set(null);this.technicalVisible.set(false);this.technicalFocused.set(false);this.pendingExisting.set(null);this.confirmationError.set('');this.dirty.set(false);
  }
  async clearCurrentDraft():Promise<void>{
    if(this.busy()||this.loading()||this.editing()||this.embedded())return;
    if(this.dirty()&&!await this.unsaved.ask())return;
    this.resetCurrentDraft();
  }
  private updateDirty():void{const baseline=this.original()?recordValues(this.definition(),this.original()!):emptyValues(this.definition());this.dirty.set(Object.keys(baseline).some(field=>this.values()[field]!==baseline[field])||((this.selected()==='tags'||this.selected()==='tag_categories')&&(this.associationChanged()||this.tagCategories.pending())));}
  setAssociationIds(ids:string[]):void{if(this.busy())return;const selected=this.selected()==='tag_categories'?this.tagIds:this.categoryIds;selected.set(uniqueSelectValues(ids));this.updateDirty();}
  constructor(){
    const destroy=inject(DestroyRef);
    afterNextRender(()=>{
      const embedded=this.embedded();
      if(embedded){this.selected.set(embedded.resource);this.values.set(emptyValues(resourceDefinitions[embedded.resource]));const ids=[embedded.parentId||pendingAssociationValue];if(embedded.resource==='tags')this.categoryIds.set(ids);else this.tagIds.set(ids);this.originalAssociationIds.set([...ids]);this.loading.set(false);embedded.ready(this);}
      else{destroy.onDestroy(this.unsaved.register(()=>this.canDeactivate()));void this.initialize();}
    });
    destroy.onDestroy(()=>this.editGeneration++);
    effect(()=>{const id=this.pendingEdit();if(id&&this.session.canCreate()&&!this.loading())untracked(()=>{this.pendingEdit.set(null);void this.openEdit(id);});});
  }
  openRelatedRegistration():void{
    if(this.embedded()||this.busy()||this.loading()||this.associationContext()||!['tags','tag_categories'].includes(this.selected())||this.editing())return;
    this.associationReturnFocus=document.activeElement as HTMLElement|null;
    const record=this.original()||this.tagCategories.currentRecord(),resource=this.association().related;
    this.associationContext.set({resource,parentId:record?recordId(this.selected(),record):'',parentName:this.values()[this.definition().display]||this.definition().label+' em cadastro',ready:form=>this.associationForm.set(form),cancelled:()=>this.finishRelatedRegistration(),completed:(related,selected)=>{
      const id=recordId(resource,related),name=related[resourceDefinitions[resource].display] as string;
      this.createdRelatedChoices.update(choices=>({...choices,[resource]:[...(choices[resource]||[]).filter(choice=>choice.value!==id),{value:id,label:name}]}));
      if(selected)this.setAssociationIds([...this.associationIds(),id]);
      this.associationRefresh.update(value=>value+1);this.finishRelatedRegistration();
    }});
    afterNextRender(()=>{const dialog=this.associationDialog()?.nativeElement;dialog?.showModal();dialog?.querySelector<HTMLButtonElement>('.icon-button')?.focus();},{injector:this.injector});
  }
  async closeRelatedRegistration():Promise<void>{const form=this.associationForm();if(!form||form.busy())return;if(await form.canDeactivate())this.finishRelatedRegistration();}
  private finishRelatedRegistration():void{this.associationDialog()?.nativeElement.close();this.associationContext.set(null);this.associationForm.set(null);afterNextRender(()=>{const trigger=document.getElementById(this.association().prefix+'-selection');(trigger||this.associationReturnFocus)?.focus();},{injector:this.injector});}
  private async initialize():Promise<void>{
    const resource=this.route.snapshot.queryParamMap.get('resource'),id=this.route.snapshot.queryParamMap.get('id');
    if(isResource(resource))this.choose(resource);
    try{const state=await this.session.ensure();if(!state.authenticated)this.session.openLogin('Entre para continuar.','/cadastros');else if(state.can_create&&id)await this.loadRecord(id);}
    catch(error){this.notice.set(safeMessage(error));if(id)this.editLoadFailed.set(true);}finally{this.loading.set(false);if(id&&!this.original()&&!this.editLoadFailed())this.pendingEdit.set(id);}
  }
  private async openEdit(id:string):Promise<void>{this.loading.set(true);this.editLoadFailed.set(false);try{await this.loadRecord(id);}catch(error){this.editLoadFailed.set(true);this.notice.set(safeMessage(error));await this.recover(error);}finally{this.loading.set(false);}}
  retryEdit():void{const id=this.route.snapshot.queryParamMap.get('id');if(id)this.pendingEdit.set(id);}
  @HostListener('window:beforeunload',['$event']) beforeUnload(event:BeforeUnloadEvent):void{if(this.hasDraftChanges()){event.preventDefault();event.returnValue='';}}
  setValue(key:string,value:string):void{this.values.update(values=>({...values,[key]:value}));this.updateDirty();this.errors.update(errors=>({...errors,[key]:''}));}
  technicalChanged(event:Event):void{this.setValue(this.definition().technical!,(event.target as HTMLInputElement).value);}
  completeName(focus:boolean):void{if(!this.definition().technical||!this.values()[this.definition().display]?.trim())return;this.technicalVisible.set(true);if(focus)afterNextRender(()=>this.technicalInput()?.nativeElement.focus(),{injector:this.injector});}
  async canDeactivate():Promise<boolean>{
    if(this.associationContext()){const form=this.associationForm();if(!form||!await form.canDeactivate())return false;this.finishRelatedRegistration();}
    if(this.busy())return false;
    if(this.hasDraftChanges()&&!await this.unsaved.ask())return false;
    this.drafts.clear();
    if(this.editing()){
      const selected=this.selected()==='tag_categories'?this.tagIds:this.categoryIds;selected.set([...this.originalAssociationIds()]);
      this.values.set(recordValues(this.definition(),this.original()!));this.errors.set({});this.failure.set(null);this.technicalVisible.set(true);this.dirty.set(false);
    }else this.resetCurrentDraft();
    return true;
  }
  async cancelForm():Promise<void>{if(!await this.canDeactivate())return;if(this.embedded()){this.embedded()!.cancelled();return;}await this.router.navigate([this.editing()?'/consultas':'/cadastrar'],{queryParams:this.editing()?{resource:this.selected()}:undefined});}
  async choose(resource:Resource):Promise<void>{
    if(resource===this.selected()||this.busy()||this.embedded()||this.associationContext())return;
    if(this.editing()){if(!await this.canDeactivate())return;}else this.storeCurrentDraft();
    this.editGeneration++;this.pendingEdit.set(null);this.editLoadFailed.set(false);this.selected.set(resource);this.original.set(null);this.restoreCurrentDraft();
  }
  another():void{this.resetCurrentDraft();}
  fieldError(key:string):string{return this.errors()[key]||(this.failure() instanceof ApiError&&(this.failure() as ApiError).details.some(detail=>detail.loc?.includes(key))?'Reveja este campo de acordo com a indicação acima.':'');}
  async loadRecord(id:string):Promise<void>{
    const resource=this.selected(),generation=++this.editGeneration,current=()=>generation===this.editGeneration&&resource===this.selected();
    const record=await this.api.request<CatalogueRecord>('/'+resource+'/'+encodeURIComponent(id));if(!current())return;
    let ids:string[]=[];
    if(resource==='tags'||resource==='tag_categories')ids=await this.tagCategories.loadExisting(record,resource,current);
    if(!current())return;
    if(resource!=='tags'&&resource!=='tag_categories')this.tagCategories.reset();
    this.categoryIds.set(resource==='tags'?[...ids]:[]);this.tagIds.set(resource==='tag_categories'?[...ids]:[]);this.originalAssociationIds.set([...ids]);
    this.original.set(record);this.values.set(recordValues(this.definition(),record));this.technicalVisible.set(!!this.definition().technical);this.dirty.set(false);this.failure.set(null);this.errors.set({});this.success.set(null);
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
    if(this.editing()&&!Object.keys(body).length&&!this.associationChanged()&&!this.tagCategories.pending()){this.notice.set('Não há alterações para guardar.');return;}
    this.busy.set(true);this.failure.set(null);this.notice.set('');
    try{
      const edited=this.editing(),path='/'+this.selected()+(edited?'/'+recordId(this.selected(),this.original()!):'');
      const record=(this.selected()==='tags'||this.selected()==='tag_categories')&&(edited?this.associationChanged()||this.tagCategories.pending():!!this.embedded()||this.associationIds().length>0||this.tagCategories.pending())
        ?await this.tagCategories.save(edited?editorPayload(definition,values):body,this.associationIds().filter(id=>id!==pendingAssociationValue),this.session.current().csrf_token,this.association().owner,this.original()||undefined,this.originalAssociationIds().filter(id=>id!==pendingAssociationValue))
        :await this.api.request<CatalogueRecord>(path,edited?'PUT':'POST',body,this.session.current().csrf_token);
      const id=recordId(this.selected(),record),name=record[definition.display];if(!id||typeof name!=='string')throw new ApiError(502);
      if(this.embedded()){const context=this.embedded()!;context.completed(record,this.associationIds().includes(context.parentId||pendingAssociationValue));return;}
      this.dirty.set(false);
      if(!edited)this.resetCurrentDraft();
      else{this.original.set(record);this.originalAssociationIds.set([...this.associationIds()]);}
      this.success.set({id,name,edited});
    }catch(error){this.failure.set(error);this.updateDirty();await this.recover(error);}finally{this.busy.set(false);}
  }
}

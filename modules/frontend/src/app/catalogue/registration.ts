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
import { AssistantForm } from '../shared/site-assistant';
import { AssistantBinding, AssistantSnapshot, AssistantSuggestion, ClassificationField, FormConversation, classificationFields } from '../shared/form-assistant';
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

@Component({selector:'app-registration',providers:[TagCategoryRegistration,RegistrationDrafts],imports:[AssistantForm,NgComponentOutlet,NgTemplateOutlet,RouterLink,Notice,CatalogueLayout,RegistrationNavigation,SharedFormField,Confirmation,NameAutocomplete,TierPosition,FieldLabel,TagCategoryField],template:`
  <ng-template #registrationContent>
    @if(!embedded()){
    <h2 id="form-choice">{{editing()?'What would you like to edit?':'What would you like to create?'}}</h2>
    <app-registration-navigation [selected]="selected()" [disabled]="busy()||loading()" (selectedChange)="choose($event)" />
    @if(!editing()&&!success()){<div class="draft-actions"><button class="text-button" type="button" [disabled]="busy()||loading()" (click)="clearCurrentDraft()">Clear all fields</button></div>}
    }
    @if(loading()){<p role="status">Loading…</p>}
    @if(notice()){<app-notice [text]="notice()" />}
    @if(editLoadFailed()){<button class="button" type="button" (click)="retryEdit()">Try opening the editor again</button>}
    @if(!loading()&&!session.canCreate()){<p class="notice" role="alert">{{session.current().authenticated?'This area requires catalogue permissions: supervisor or administrator.':'Sign in to continue. Your entered values are preserved.'}}</p><button class="button" type="button" (click)="session.openLogin('Sign in to continue.','/registrations')">Sign in</button>}
    @if(success();as result){<section class="success" role="status"><span class="success-icon" aria-hidden="true">✓</span><h2>{{result.edited?'Changes saved!':'Created successfully!'}}</h2><p>{{result.name}}</p><p class="record-id">Identifier <strong>{{result.id}}</strong></p>
      @if(result.edited){<a class="button button-primary" routerLink="/catalogue" [queryParams]="{resource:selected()}">Back to results ↗</a>}
      @else{<button class="button button-primary" type="button" (click)="another()">Create another ↗</button>}
    </section>}
    @else{<form appAssistantForm [assistantBinding]="selected()==='work_classifications'?classificationAssistant:null" (submit)="$event.stopPropagation();submit($event)"><p class="required-note"><strong class="required-star" aria-hidden="true">*</strong> Required field</p><fieldset [disabled]="busy()||loading()||editLoadFailed()||!session.canCreate()">
      <app-name-autocomplete [definition]="definition()" [value]="values()[definition().display]||''" (valueChange)="setValue(definition().display,$event)" [error]="fieldError(definition().display)" [enabled]="!editing()&&selected()!=='tag_categories'&&!tagCategories.pending()" (selected)="pendingExisting.set($event)" (completed)="completeName($event)" />
      @if(definition().technical && technicalVisible()){
        <div class="field"><app-field-label [fieldId]="definition().technical!" label="Technical name" [required]="editing()||!suggestion()" [help]="'Use lowercase ASCII letters, numbers and underscores between words.'+(editing()?'':' Leave blank to use the valid suggestion; focus to enter your own name.')" /><input #technicalInput [id]="definition().technical" [value]="values()[definition().technical!]||''" (input)="technicalChanged($event)" (focus)="technicalFocused.set(true)" (blur)="technicalFocused.set(false)" [placeholder]="technicalFocused()?'':suggestion()" [required]="editing()||!suggestion()" aria-required="true" [attr.aria-describedby]="definition().technical+'-help '+definition().technical+'-error'" [attr.aria-invalid]="fieldError(definition().technical!)?'true':null" pattern="[a-z][a-z0-9]*(_[a-z0-9]+)*">
        @if(!editing()&&!suggestion()&&!values()[definition().technical!]){<p class="field-error">Could not generate a valid technical name. Enter a technical name.</p>}
        <p class="field-error" [id]="definition().technical+'-error'">{{fieldError(definition().technical!)}}</p></div>
      }
      @for(field of definition().fields;track field.key){
        @if(field.key==='tier'){<app-tier-position [editing]="editing()" [value]="values()['tier']||''" (valueChange)="setValue('tier',$event)" [error]="fieldError('tier')" (available)="tierReady.set($event)" />}
        @else if((field.key!=='platform_url'||values()['platform_access_types']==='website')&&(field.key!=='price_amount'||values()['platform_is_paid']==='true')&&(field.key!=='price_currency'||hasPrice())){<app-form-field [definition]="field" [requiredOverride]="field.key==='price_currency'&&hasPrice()" [value]="values()[field.key]||''" (valueChange)="setValue(field.key,$event)" [error]="fieldError(field.key)" />}
      }
      @if(selected()==='tags'||selected()==='tag_categories'){
        <app-tag-category-field [owner]="association().owner" [value]="associationIds()" (valueChange)="setAssociationIds($event)" [error]="fieldError(association().relatedKey)" [disabled]="busy()||tagCategories.uncertain()" [allowCreate]="!embedded()&&!editing()" (createRequested)="openRelatedRegistration()" [extraChoices]="relatedChoices()" [refresh]="associationRefresh()" />
        @if(embedded()&&!embedded()!.parentId){<p class="help">{{pendingAssociationMessage()}}</p>}
        @if(editing()&&tagCategories.pending()&&!busy()){<p class="notice" role="status">Some changes may already be saved. Your selections are preserved; try Save changes again to complete the links. Leaving does not undo saved changes.</p>}
        @if(selected()==='tags'){
          @if(tagCategories.created()){<p class="notice" role="status">The Tag has been created. Complete its categories with Create; retries reuse the same Tag. Leaving preserves saved data.</p>}
          @if(tagCategories.uncertain()){<p class="form-error" role="alert">Could not confirm Tag creation. Check Browse before trying again; the request will not be repeated automatically.</p>}
        }@else{
          @if(tagCategories.created()){<p class="notice" role="status">The Tag Category has been created. Complete its links with Create; retries reuse the same category. Leaving preserves saved data.</p>}
          @if(tagCategories.uncertain()){<p class="form-error" role="alert">Could not confirm category creation. Check whether it was created before trying again; the request will not be repeated automatically.</p>}
        }
      }
      @if(failure()){<p class="form-error" role="alert">{{errorMessage()}}</p>}
      <div class="dialog-actions form-actions"><button class="button" type="button" [disabled]="busy()" (click)="cancelForm()">Cancel</button><button class="button button-primary" [attr.aria-busy]="busy()" type="submit">{{busy()?'Saving…':editing()?'Save changes':'Create'}}</button></div>
    </fieldset></form>}
  </ng-template>
  @if(embedded()){
    <ng-container [ngTemplateOutlet]="registrationContent" />
  }@else{
    <app-catalogue-layout [singleBackLink]="!editing()||selected()==='platforms'" [class.platform-registration]="selected()==='platforms'" [title]="title()" subtitle="A platform, tag or Work Classification for your catalogue." [back]="editing()?'/catalogue':'/create'" [backLabel]="editing()?'Back to results':'Back to Create'">
      <ng-container [ngTemplateOutlet]="registrationContent" />
    </app-catalogue-layout>
  }
  @if(associationContext();as context){
    <dialog #associationDialog class="modal category-create-modal" aria-labelledby="association-modal-title" (cancel)="$event.preventDefault();closeRelatedRegistration()">
      <div class="modal-content"><div class="modal-top"><h2 id="association-modal-title">{{registrationTitles[context.resource]}}</h2><button class="icon-button" type="button" [attr.aria-label]="'Close creation of '+resourceDefinitions[context.resource].noun" [disabled]="associationBusy()" (click)="closeRelatedRegistration()">×</button></div>
        <ng-container *ngComponentOutlet="registrationComponent;inputs:{embedded:context}" />
      </div>
    </dialog>
  }
  @if(pendingExisting();as item){<app-confirmation [title]="'This '+definition().noun+' already exists. Would you like to edit it?'" [name]="item[definition().display]+''" action="Edit" [busy]="busy()" [error]="confirmationError()" (cancelled)="pendingExisting.set(null);confirmationError.set('')" (confirmed)="confirmExisting()" />}
  @if(pendingAssistantChange();as pending){<app-confirmation title="Apply suggestions over manually entered values?" [name]="pending.description" action="Apply suggestions" cancelLabel="Cancel and keep my values" (cancelled)="decideAssistantChange(false)" (confirmed)="decideAssistantChange(true)" />}
`})
export class Registration {
  readonly classificationConversation=new FormConversation();
  readonly pendingAssistantChange=signal<{description:string;resolve:(accepted:boolean)=>void}|null>(null);
  readonly classificationAssistant:AssistantBinding={
    assistantId:'assistant_2',
    conversation:this.classificationConversation,
    available:()=>this.selected()==='work_classifications'&&!this.busy()&&!this.loading()&&!this.editLoadFailed()&&!this.success()&&!this.pendingExisting()&&this.tierReady()&&this.session.canCreate(),
    snapshot:()=>({mode:this.editing()?'edit':'create',technical_visible:this.technicalVisible(),record_id:this.original()?recordId(this.selected(),this.original()!):null,epoch:this.classificationConversation.epoch,values:Object.fromEntries(classificationFields.map(field=>[field,this.values()[field]||''])) as Record<ClassificationField,string>}),
    fields:()=>[
      {key:this.definition().display,label:'Display Name',required:true,valid:!!this.values()[this.definition().display]?.trim()},
      {key:this.definition().technical!,label:'Technical Name',required:true,generated:true,valid:technicalPattern.test(effectiveTechnical(this.definition(),this.values(),this.editing()))},
      ...this.definition().fields.map(field=>({key:field.key,label:field.label,required:!!field.required||field.key==='tier'&&this.editing(),valid:field.key==='tier'?this.tierReady()&&(!this.editing()&&!this.values()['tier']||/^[1-9][0-9]*$/.test(this.values()['tier']||'')):!this.fieldError(field.key)&&(!field.key.startsWith('description_')||!descriptionError(this.values()[field.key]||''))}))],
    apply:(result,snapshot,current,abortSignal)=>this.applyAssistantSuggestion(result,snapshot,current,abortSignal)
  };
  decideAssistantChange(accepted:boolean):void{const pending=this.pendingAssistantChange();this.pendingAssistantChange.set(null);pending?.resolve(accepted);}
  private async applyAssistantSuggestion(result:AssistantSuggestion,snapshot:AssistantSnapshot,current:()=>boolean,abortSignal:AbortSignal):Promise<boolean>{
    if(!current()||!this.classificationAssistant.available()||snapshot.mode!==(this.editing()?'edit':'create'))return false;
    const changes=result.proposals.map(item=>({field:item.field,value:item.value===null?'':String(item.value)})).filter(item=>this.values()[item.field]!==item.value);
    if(!changes.length)return true;
    const before={...this.values()};
    const protectedChanges=changes.filter(item=>this.classificationConversation.manualFields.has(item.field)||before[item.field]!==snapshot.values[item.field]||(!!before[item.field]&&this.classificationConversation.appliedValues.get(item.field)!==before[item.field]));
    if(protectedChanges.length){
      const labels:Record<ClassificationField,string>={display_name_work_classifications:'Display Name',work_classification_name:'Technical Name',description_work_classifications:'Description',tier:'Position'};
      const accepted=await new Promise<boolean>(resolve=>{
        const finish=(value:boolean)=>{abortSignal.removeEventListener('abort',cancel);resolve(value);};
        const cancel=()=>this.decideAssistantChange(false);
        abortSignal.addEventListener('abort',cancel,{once:true});
        this.pendingAssistantChange.set({description:'The suggestion changes manually entered values in: '+protectedChanges.map(item=>labels[item.field]).join(', ')+'. Apply these changes?',resolve:finish});
        if(abortSignal.aborted)cancel();
      });
      if(!accepted)return false;
    }
    if(!current()||!this.classificationAssistant.available()||changes.some(item=>this.values()[item.field]!==before[item.field]))return false;
    this.values.update(values=>({...values,...Object.fromEntries(changes.map(item=>[item.field,item.value]))}));
    for(const item of changes){this.classificationConversation.appliedValues.set(item.field,item.value);this.classificationConversation.manualFields.delete(item.field);}
    if(changes.some(item=>item.field==='work_classification_name'||item.field==='tier'))this.technicalVisible.set(true);
    this.errors.update(errors=>({...errors,...Object.fromEntries(changes.map(item=>[item.field,'']))}));this.updateDirty();
    return true;
  }
  readonly registrationTitles=registrationTitles;readonly resourceDefinitions=resourceDefinitions;
  readonly embedded=input<EmbeddedAssociation|null>(null);
  readonly registrationComponent=Registration;
  readonly associationContext=signal<EmbeddedAssociation|null>(null);readonly associationRefresh=signal(0);
  private readonly associationForm=signal<Registration|null>(null);private associationReturnFocus:HTMLElement|null=null;
  private readonly createdRelatedChoices=signal<Partial<Record<TagCategoryOwner,{value:string;label:string}[]>>>({});
  private readonly associationDialog=viewChild<ElementRef<HTMLDialogElement>>('associationDialog');
  readonly associationBusy=computed(()=>!!this.associationContext()&&!!this.associationForm()?.busy());
  readonly relatedChoices=computed(()=>{const context=this.embedded();return context?[{value:context.parentId||pendingAssociationValue,label:context.parentName}]:this.createdRelatedChoices()[this.association().related]||[];});
  readonly pendingAssociationMessage=computed(()=>this.embedded()?.resource==='tags'?'The Tag Category has not been saved yet. Its link will be created when you save the category.':'The Tag has not been saved yet. Its link will be created when you save the Tag.');
  readonly session=inject(Session);private readonly api=inject(Api);private readonly route=inject(ActivatedRoute);private readonly injector=inject(Injector);
  private readonly router=inject(Router);private readonly unsaved=inject(UnsavedChanges);
  readonly selected=signal<Resource>('platforms');readonly definition=computed(()=>resourceDefinitions[this.selected()]);
  readonly title=computed(()=>this.editing()?'Edit '+this.definition().label:registrationTitles[this.selected()]);
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
    if(this.selected()==='work_classifications')this.classificationConversation.reset();
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
    this.associationContext.set({resource,parentId:record?recordId(this.selected(),record):'',parentName:this.values()[this.definition().display]||this.definition().label+' being created',ready:form=>this.associationForm.set(form),cancelled:()=>this.finishRelatedRegistration(),completed:(related,selected)=>{
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
    try{const state=await this.session.ensure();if(!state.authenticated)this.session.openLogin('Sign in to continue.','/registrations');else if(state.can_create&&id)await this.loadRecord(id);}
    catch(error){this.notice.set(safeMessage(error));if(id)this.editLoadFailed.set(true);}finally{this.loading.set(false);if(id&&!this.original()&&!this.editLoadFailed())this.pendingEdit.set(id);}
  }
  private async openEdit(id:string):Promise<void>{this.loading.set(true);this.editLoadFailed.set(false);try{await this.loadRecord(id);}catch(error){this.editLoadFailed.set(true);this.notice.set(safeMessage(error));await this.recover(error);}finally{this.loading.set(false);}}
  retryEdit():void{const id=this.route.snapshot.queryParamMap.get('id');if(id)this.pendingEdit.set(id);}
  @HostListener('window:beforeunload',['$event']) beforeUnload(event:BeforeUnloadEvent):void{if(this.hasDraftChanges()){event.preventDefault();event.returnValue='';}}
  setValue(key:string,value:string):void{if(this.selected()==='work_classifications')this.classificationConversation.manualFields.add(key);this.values.update(values=>({...values,[key]:value}));this.updateDirty();this.errors.update(errors=>({...errors,[key]:''}));}
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
  async cancelForm():Promise<void>{if(!await this.canDeactivate())return;if(this.embedded()){this.embedded()!.cancelled();return;}await this.router.navigate([this.editing()?'/catalogue':'/create'],{queryParams:this.editing()?{resource:this.selected()}:undefined});}
  async choose(resource:Resource):Promise<void>{
    if(resource===this.selected()||this.busy()||this.embedded()||this.associationContext())return;
    if(this.editing()){if(!await this.canDeactivate())return;}else this.storeCurrentDraft();
    this.editGeneration++;this.pendingEdit.set(null);this.editLoadFailed.set(false);this.selected.set(resource);this.original.set(null);this.restoreCurrentDraft();
  }
  another():void{this.resetCurrentDraft();}
  fieldError(key:string):string{return this.errors()[key]||(this.failure() instanceof ApiError&&(this.failure() as ApiError).details.some(detail=>detail.loc?.includes(key))?'Review this field using the guidance above.':'');}
  async loadRecord(id:string):Promise<void>{
    const resource=this.selected(),generation=++this.editGeneration,current=()=>generation===this.editGeneration&&resource===this.selected();
    const record=await this.api.request<CatalogueRecord>('/'+resource+'/'+encodeURIComponent(id));if(!current())return;
    let ids:string[]=[];
    if(resource==='tags'||resource==='tag_categories')ids=await this.tagCategories.loadExisting(record,resource,current);
    if(!current())return;
    if(resource==='work_classifications')this.classificationConversation.reset();
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
    if(!this.session.current().authenticated){this.session.openLogin('Sign in again; your values are preserved.','/registrations');return;}
    if(!this.session.canCreate()){this.notice.set('This area requires catalogue permissions: supervisor or administrator.');return;}
    const definition=this.definition(),values=this.values(),errors:Record<string,string>={};
    if(!values[definition.display]?.trim())errors[definition.display]='Enter a display name.';
    for(const field of definition.fields){
      if(field.kind==='access'&&field.required&&!values[field.key])errors[field.key]='Select an option.';
      if(field.kind==='decimal'&&values['platform_is_paid']==='true'&&priceError(values[field.key]||''))errors[field.key]=priceError(values[field.key]||'');
      if(field.key.startsWith('description_')&&(!this.original()||values[field.key]!==recordValues(definition,this.original()!)[field.key])){const error=descriptionError(values[field.key]||'');if(error)errors[field.key]=error;}
    }
    if(this.selected()==='platforms'&&this.hasPrice()&&!currencies.some(choice=>choice.code===values['price_currency'])&&!(this.editing()&&values['price_currency']===this.original()?.['price_currency']&&!!values['price_currency']))errors['price_currency']='Select an option.';
    if(this.selected()==='work_classifications'&&!this.tierReady())errors['tier']='Wait for the complete order or choose Refresh order before saving.';
    if(definition.technical&&!technicalPattern.test(effectiveTechnical(definition,values,this.editing()))){errors[definition.technical]='Enter a valid technical name: lowercase ASCII letters and underscores between words.';this.technicalVisible.set(true);}
    if(values['tier']&&(!/^[1-9][0-9]*$/.test(values['tier'])||!Number.isSafeInteger(Number(values['tier']))))errors['tier']='Use a positive integer position.';
    this.errors.set(errors);if(Object.keys(errors).length)return;
    const body=editorPayload(definition,values,this.original()||undefined);
    if(this.editing()&&!Object.keys(body).length&&!this.associationChanged()&&!this.tagCategories.pending()){this.notice.set('There are no changes to save.');return;}
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

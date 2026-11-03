import { Injectable, computed, signal } from '@angular/core';

export const classificationFields=['display_name_work_classifications','work_classification_name','description_work_classifications','tier'] as const;
export type ClassificationField=typeof classificationFields[number];
export interface AssistantMessage {role:'user'|'assistant';content:string;}
export interface AssistantProposal {field:ClassificationField;value:string|number|null;}
export interface AssistantSuggestion {reply:string;proposals:AssistantProposal[];missing_fields:ClassificationField[];}
export interface AssistantSnapshot {mode:'create'|'edit';values:Record<ClassificationField,string>;epoch:number;}
export class FormConversation {
  epoch=0;
  readonly history=signal<AssistantMessage[]>([]);
  readonly manualFields=new Set<string>();
  readonly appliedValues=new Map<string,string>();
  reset():void{this.epoch++;this.history.set([]);this.manualFields.clear();this.appliedValues.clear();}
}
export interface AssistantBinding {
  conversation:FormConversation;
  available:()=>boolean;
  snapshot:()=>AssistantSnapshot;
  apply:(result:AssistantSuggestion,snapshot:AssistantSnapshot,current:()=>boolean,signal:AbortSignal)=>Promise<boolean>;
}

/** Match the assistant to the rendered form, including nested modal lifetimes. */
@Injectable({providedIn:'root'})
export class FormAssistantBridge {
  private readonly forms=signal<readonly {element:HTMLFormElement;binding:AssistantBinding|null}[]>([]);
  readonly active=computed(()=>this.forms().at(-1)?.binding||null);
  bind(element:HTMLFormElement,binding:AssistantBinding|null):void{
    this.forms.update(forms=>forms.some(item=>item.element===element)?forms.map(item=>item.element===element?{element,binding}:item):[...forms,{element,binding}]);
  }
  remove(element:HTMLFormElement):void{this.forms.update(forms=>forms.filter(item=>item.element!==element));}
}

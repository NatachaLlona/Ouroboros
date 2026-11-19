import { Injectable, computed, signal } from '@angular/core';
import { assistantIds } from './assistant-identity';

export const classificationFields=['display_name_work_classifications','work_classification_name','description_work_classifications','tier'] as const;
export type ClassificationField=typeof classificationFields[number];
export interface AssistantMessage {assistant_id?:typeof assistantIds.forms;role:'user'|'assistant';content:string;}
export interface AssistantProposal {field:ClassificationField;value:string|number|null;}
export interface AssistantSuggestion {reply:string;proposals:AssistantProposal[];missing_fields:ClassificationField[];optional_declined?:boolean;position_confirmation?:{token:string;message:string}|null;notice?:string|null;}
export interface AssistantSnapshot {mode:'create'|'edit';values:Record<ClassificationField,string>;epoch:number;record_id?:string|null;technical_visible?:boolean;}
export interface AssistantFieldStatus {key:string;label:string;required:boolean;valid:boolean;generated?:boolean;}
export class FormConversation {
  readonly assistantId=assistantIds.forms;
  epoch=0;
  readonly history=signal<AssistantMessage[]>([]);
  readonly manualFields=new Set<string>();
  readonly appliedValues=new Map<string,string>();
  optionalStatus:'unoffered'|'offered'|'declined'='unoffered';
  reset():void{this.epoch++;this.history.set([]);this.manualFields.clear();this.appliedValues.clear();this.optionalStatus='unoffered';}
}
export interface AssistantBinding {
  readonly assistantId:typeof assistantIds.forms;
  conversation:FormConversation;
  available:()=>boolean;
  snapshot:()=>AssistantSnapshot;
  apply:(result:AssistantSuggestion,snapshot:AssistantSnapshot,current:()=>boolean,signal:AbortSignal)=>Promise<boolean>;
  fields?:()=>AssistantFieldStatus[];
}

export function validAssistantSuggestion(result:AssistantSuggestion):boolean{
  return !!result&&typeof result.reply==='string'&&result.reply.length<=4500&&Array.isArray(result.proposals)&&result.proposals.length<=4&&
    result.proposals.every(item=>classificationFields.includes(item.field)&&(item.value===null||typeof item.value==='string'||typeof item.value==='number'&&Number.isSafeInteger(item.value)))&&
    new Set(result.proposals.map(item=>item.field)).size===result.proposals.length&&
    (!result.position_confirmation||typeof result.position_confirmation.token==='string'&&result.position_confirmation.token.length<=100&&typeof result.position_confirmation.message==='string');
}

/** Acknowledge actual values after application, never a model's predicted success. */
export function applicationReply(binding:AssistantBinding,result:AssistantSuggestion,before:AssistantSnapshot):string{
  const after=binding.snapshot(),fields:AssistantFieldStatus[]=binding.fields?.()||classificationFields.map(key=>({key,label:key,required:false,valid:true}));
  const applied=result.proposals.filter(item=>after.values[item.field]===(item.value===null?'':String(item.value)));
  const pending=result.proposals.filter(item=>!applied.includes(item));
  const labels=(items:AssistantProposal[])=>items.map(item=>fields.find(field=>field.key===item.field)?.label||item.field).join(', ');
  const parts:string[]=[];
  if(applied.length)parts.push('Fields verified in the form: '+labels(applied)+'. You can adjust them before saving.');
  if(pending.length)parts.push('Not applied: '+labels(pending)+'. Your current values are preserved.');
  if(result.notice)parts.push(result.notice);
  else if(!result.proposals.length&&!/preenchi|apliquei|salvei|cadastr[ae]i|filled|saved|applied|nome t[eé]cnico|technical name/i.test(result.reply)&&(!binding.fields||!result.reply.includes('?')))parts.push(result.reply);
  if(applied.some(item=>item.field.startsWith('description_')&&!before.values[item.field]))parts.push('I suggested a description based on your message; you can adjust it.');
  if(result.optional_declined)binding.conversation.optionalStatus='declined';
  const missing=fields.find(field=>field.required&&!field.valid&&!field.generated);
  if(missing)parts.push('What is the value of '+missing.label+'?');
  else if(fields.some(field=>field.required&&!field.valid&&field.generated))parts.push('Review the automatic suggestion in the form before saving.');
  else if(binding.fields&&binding.conversation.optionalStatus==='unoffered'){
    const optional=fields.filter(field=>!field.required&&!field.generated).map(field=>field.label);
    if(optional.length){parts.push('Required fields are complete. Would you like to adjust optional fields ('+optional.join(', ')+'), or would you prefer to leave them unchanged?');binding.conversation.optionalStatus='offered';}
  }
  return parts.filter(Boolean).join('\n')||'Your current values are preserved. You can adjust the form before saving.';
}

/** Match the assistant to the rendered form, including nested modal lifetimes. */
@Injectable({providedIn:'root'})
export class FormAssistantBridge {
  private readonly forms=signal<readonly {element:HTMLFormElement;binding:AssistantBinding|null}[]>([]);
  readonly active=computed(()=>{const binding=this.forms().at(-1)?.binding;return binding?.assistantId===assistantIds.forms&&binding.conversation.assistantId===assistantIds.forms?binding:null;});
  bind(element:HTMLFormElement,binding:AssistantBinding|null):void{
    this.forms.update(forms=>forms.some(item=>item.element===element)?forms.map(item=>item.element===element?{element,binding}:item):[...forms,{element,binding}]);
  }
  remove(element:HTMLFormElement):void{this.forms.update(forms=>forms.filter(item=>item.element!==element));}
}

import { Resource } from './models';
import { publicContracts } from './contracts.generated';
import { priceError, priceRecordText, priceValue } from '../shared/money';
import { FANTASY_NAME_LABEL, PRICE_HELP_TEXT } from '../shared/field-label';

export interface FieldDefinition { key: string; label: string; kind: 'text' | 'textarea' | 'boolean' | 'access' | 'decimal' | 'currency' | 'integer' | 'url'; required?: boolean; help?: string; }
export interface ResourceDefinition {
  resource: Resource; label: string; noun: string; display: string; technical?: string; fields: readonly FieldDefinition[];
}
export const resourceDefinitions: Record<Resource, ResourceDefinition> = {
  platforms: {resource:'platforms',label:'Plataforma',noun:'plataforma',display:'platform_name',fields:[
    {key:'platform_access_types',label:'Onde acessar',kind:'access',required:true},
    {key:'platform_url',label:'URL',kind:'url',help:'Use HTTP/HTTPS, até 2083 caracteres.'},
    {key:'platform_is_episodes',label:'Conteúdo em episódios',kind:'boolean'},
    {key:'platform_is_duration_time',label:'Conteúdo com duração',kind:'boolean'},
    {key:'platform_is_paid',label:'Plataforma paga',kind:'boolean'},
    {key:'price_amount',label:'Preço',kind:'decimal',help:PRICE_HELP_TEXT},
    {key:'price_currency',label:'Moeda',kind:'currency'}
  ]},
  tags: {resource:'tags',label:'Tag',noun:'tag',display:'display_name_tags',technical:'tag_name',fields:[
    {key:'description_tags',label:'Descrição',kind:'textarea'}
  ]},
  work_classifications: {resource:'work_classifications',label:'Classificação da Obra',noun:'classificação',display:'display_name_work_classifications',technical:'work_classification_name',fields:[
    {key:'description_work_classifications',label:'Descrição',kind:'textarea'},
    {key:'tier',label:'Posição (tier)',kind:'integer',help:'Ao criar, vazio adiciona no fim. Uma posição insere ou move e o servidor reordena as restantes classificações numa transação.'}
  ]}
};
export const resources = Object.values(resourceDefinitions);
export type EditorValues = Record<string, string>;
export function hasValidPrice(values:EditorValues):boolean {
  return values['platform_is_paid']==='true'&&!!values['price_amount']?.trim()&&!priceError(values['price_amount']);
}
export type CatalogueRecord = Record<string, unknown>;
export interface CataloguePage { count: number; page: number; page_size: number; items: CatalogueRecord[]; }
export const technicalPattern = /^[a-z][a-z0-9]*(_[a-z0-9]+)*$/;
export function technicalSuggestion(value: string): string {
  const candidate = value.normalize('NFKD').replace(/\p{M}/gu,'').toLowerCase().replace(/[^a-z0-9]+/g,'_').replace(/^_+|_+$/g,'');
  return technicalPattern.test(candidate) ? candidate : '';
}
export function substringPattern(value: string): string { return '%' + value.replace(/[\\%_]/g, match => '\\' + match) + '%'; }
export function isResource(value: string | null): value is Resource { return value !== null && Object.hasOwn(resourceDefinitions,value); }
export function recordId(resource: Resource, record: CatalogueRecord): string { const value=record['id_'+resource];return typeof value==='string'&&/^[A-Z]+[0-9]+$/.test(value)?value:''; }
export function emptyValues(definition: ResourceDefinition): EditorValues {
  return Object.fromEntries([[definition.display,''],...(definition.technical ? [[definition.technical,'']] : []),...definition.fields.map(field=>[field.key,field.kind==='boolean'?'false':''])]);
}
export function recordValues(definition: ResourceDefinition, record: CatalogueRecord): EditorValues {
  const values=emptyValues(definition);
  for (const key of Object.keys(values)) values[key]=Array.isArray(record[key]) ? (record[key] as string[]).join(',') : record[key] == null ? '' : String(record[key]);
  if (definition.resource==='platforms') values['price_amount']=priceRecordText(values['price_amount']);
  return values;
}
export function effectiveTechnical(definition: ResourceDefinition, values: EditorValues, editing: boolean): string {
  return definition.technical ? values[definition.technical] || (editing ? '' : technicalSuggestion(values[definition.display] || '')) : '';
}
export function editorPayload(definition: ResourceDefinition, values: EditorValues, original?: CatalogueRecord): CatalogueRecord {
  const result: CatalogueRecord = {[definition.display]:values[definition.display]};
  if (definition.technical) result[definition.technical]=effectiveTechnical(definition,values,!!original);
  for (const field of definition.fields) {
    if(!original&&definition.resource==='platforms'&&values['platform_is_paid']!=='true'&&['price_amount','price_currency'].includes(field.key))continue;
    if(!original&&definition.resource==='platforms'&&field.kind==='currency'&&!hasValidPrice(values))continue;
    const value=values[field.key] || '';
    if (field.kind==='boolean') {if(value!=='true'&&value!=='false')throw new Error('Unanswered required boolean');result[field.key]=value==='true';}
    else if (field.kind==='decimal') result[field.key]=priceValue(value);
    else if (field.kind==='access') result[field.key]=value ? value.split(',') : [];
    else if (field.kind==='integer') { if (value) result[field.key]=Number(value); else if (original) result[field.key]=null; }
    else result[field.key]=value || null;
  }
  if(!original&&definition.resource==='platforms'&&!values['price_amount']?.trim())delete result['price_amount'];
  if (definition.resource==='platforms'&&values['platform_access_types']!=='website') {
    if (!original) delete result['platform_url'];
    else if (values['platform_access_types']===recordValues(definition,original)['platform_access_types']) delete result['platform_url'];
    else result['platform_url']=null;
  }
  if (original) {
    const previous=recordValues(definition,original);
    for (const key of Object.keys(result)) if (values[key]===previous[key]) delete result[key];
    if (definition.resource==='platforms'&&values['platform_access_types']!==previous['platform_access_types']&&values['platform_access_types']!=='website') result['platform_url']=null;
  }
  return result;
}
export function contract(resource: Resource) { return publicContracts[resource]; }
export function filterLabel(key: string, definition: ResourceDefinition): string {
  if (key===definition.display) return FANTASY_NAME_LABEL;
  if (key===definition.technical) return 'Nome técnico (exato)';
  if (key.startsWith('id_')) return 'Identificador';
  if (key.startsWith('sequence_')) return 'Sequência';
  if (key.startsWith('prefix_')) return 'Prefixo';
  if (key.startsWith('fantasy_name_')) return 'Nome fixo da tabela';
  return ({created_at:'Criação — instante exato',created_at_timezone:'Fuso registado na criação',created_at_date:'Criação — dia exato',created_at_from:'Criação — início',created_at_to:'Criação — fim inclusivo para datas',filter_timezone:'Fuso dos filtros (IANA)'} as Record<string,string>)[key] || definition.fields.find(field=>field.key===key)?.label || key;
}

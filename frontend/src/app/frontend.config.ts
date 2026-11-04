/** Public presentation only; defaults and runtime schema share one public document. */
import defaults from "../../public/runtime-config.json";
export const frontendConfig={...defaults};

/** Loaded before bootstrap; public presentation never accepts service credentials. */
export async function loadFrontendConfig():Promise<void>{
  const response=await fetch('/frontend/runtime-config.json',{cache:'no-store',credentials:'same-origin'});
  if(!response.ok)throw new Error('Public frontend configuration unavailable');
  const config:unknown=await response.json();
  if(!config||typeof config!=='object'||Array.isArray(config))throw new Error('Invalid public configuration');
  const document=config as Record<string,unknown>;
  if(Object.keys(document).sort().join()!==Object.keys(frontendConfig).sort().join())throw new Error('Invalid public configuration keys');
  for(const [key,defaultValue] of Object.entries(frontendConfig)){
    const value=document[key];
    if(typeof defaultValue==='string'){
      if(typeof value!=='string'||!value.trim()||value.length>4000)throw new Error('Invalid public configuration text');
      if(key.endsWith('_image')&&(!/^\/frontend\/[a-zA-Z0-9_./-]+$/.test(value)||value.includes('..')))throw new Error('Invalid public image path');
    }else{
      if(!value||typeof value!=='object'||Object.keys(value).sort().join()!==Object.keys(defaultValue).sort().join()||Object.values(value).some(color=>typeof color!=='string'||!/^#[0-9a-f]{6}$/i.test(color)))throw new Error('Invalid public colors');
    }
  }
  Object.assign(frontendConfig,document);
}

export function assistantGreeting(formAssistant:boolean):string{
  const template=formAssistant?frontendConfig.mensagem_boas_vindas_assistente_2:frontendConfig.mensagem_boas_vindas_assistente;
  return template.replaceAll('{nome_assistente}',frontendConfig.nome_assistente).replaceAll('{nome_assistente_2}',frontendConfig.nome_assistente_2);
}

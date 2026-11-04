/** Compile public assistant colors into external CSS without weakening CSP. */
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const frontendConfig=JSON.parse(readFileSync(process.argv[2]||resolve(root,'public/runtime-config.json'),'utf8'));
const properties={text:'--assistant-text',highlighted_text:'--assistant-highlighted-text',primary:'--assistant-primary',accent:'--assistant-accent',user_text:'--assistant-user-text'};
const lines=['/* Generated from public runtime configuration; do not edit manually. */'];
const expected=['nome_assistente','nome_assistente_2','mensagem_boas_vindas_assistente','mensagem_boas_vindas_assistente_2','assistant_colors','assistant_2_colors','assistant_image','assistant_2_image','balloon_image'];
if(Object.keys(frontendConfig).sort().join()!==expected.sort().join())throw new Error('Unexpected public configuration keys');
for(const key of ['nome_assistente','nome_assistente_2','mensagem_boas_vindas_assistente','mensagem_boas_vindas_assistente_2']){
  if(typeof frontendConfig[key]!=='string'||!frontendConfig[key].trim()||frontendConfig[key].length>4000)throw new Error('Invalid public presentation text');
}
for(const key of ['assistant_image','assistant_2_image','balloon_image']){
  if(typeof frontendConfig[key]!=='string'||!/^\/frontend\/[a-zA-Z0-9_./-]+$/.test(frontendConfig[key])||frontendConfig[key].includes('..'))throw new Error('Invalid public image path');
}
for(const [context,colors] of [['general',frontendConfig.assistant_colors],['forms',frontendConfig.assistant_2_colors]]){
  if(Object.keys(colors||{}).sort().join()!==Object.keys(properties).sort().join())throw new Error('Invalid public color keys');
  const declarations=Object.entries(properties).map(([key,property])=>{
    if(typeof colors?.[key]!=='string'||!/^#[0-9a-f]{6}$/i.test(colors[key]))throw new Error('Assistant colors must be six-digit hexadecimal colors');
    return property+':'+colors[key];
  });
  declarations.push(`--assistant-balloon-image:url('${frontendConfig.balloon_image}')`);
  lines.push(`app-site-assistant[data-assistant="${context}"]{${declarations.join(';')}}`);
}
const css=lines.join('\n')+'\n';
if(process.argv[3])writeFileSync(process.argv[3],css);
else{
  writeFileSync(resolve(root,'styles/assistant-theme.generated.css'),css);
  writeFileSync(resolve(root,'public/assistant-theme.css'),css);
}

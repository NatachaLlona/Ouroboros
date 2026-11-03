/** Compile public assistant colors into external CSS without weakening CSP. */
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';

const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const source=readFileSync(resolve(root,'src/app/frontend.config.ts'),'utf8');
const code=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.ES2022,target:ts.ScriptTarget.ES2022}}).outputText;
const {frontendConfig}=await import('data:text/javascript;base64,'+Buffer.from(code).toString('base64'));
const properties={text:'--assistant-text',highlighted_text:'--assistant-highlighted-text',primary:'--assistant-primary',accent:'--assistant-accent',user_text:'--assistant-user-text'};
const lines=['/* Generated from frontend.config.ts; do not edit manually. */'];
for(const [context,colors] of [['general',frontendConfig.assistant_colors],['forms',frontendConfig.assistant_2_colors]]){
  const declarations=Object.entries(properties).map(([key,property])=>{
    if(typeof colors?.[key]!=='string'||!/^#[0-9a-f]{6}$/i.test(colors[key]))throw new Error('Assistant colors must be six-digit hexadecimal colors');
    return property+':'+colors[key];
  });
  lines.push(`app-site-assistant[data-assistant="${context}"]{${declarations.join(';')}}`);
}
writeFileSync(resolve(root,'styles/assistant-theme.generated.css'),lines.join('\n')+'\n');

/** Attach reproducible public provenance to the completed Angular build. */
import { createHash } from 'node:crypto';
import { readFileSync, readdirSync, writeFileSync, renameSync, unlinkSync } from 'node:fs';
import { dirname, resolve, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const build=resolve(root,'dist/browser');
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
let html=readFileSync(resolve(build,'index.html'),'utf8');
const queue=[...html.matchAll(/(?:src|href)="(\/frontend\/[^"?]+\.(?:js|css))"/g)].map(match=>match[1]);
const assets=new Map();
while(queue.length){
  const url=queue.shift();if(assets.has(url))continue;
  if(!/^\/frontend\/[A-Za-z0-9_-]+\.(?:js|css)$/.test(url))throw new Error('Unexpected build asset path');
  const bytes=readFileSync(resolve(build,url.slice('/frontend/'.length)));
  assets.set(url,{url,sha256:hash(bytes),bytes:bytes.length});
  if(url.endsWith('.js'))for(const match of bytes.toString('utf8').matchAll(/["'`](?:\.\/|\/frontend\/)?((?:chunk|main)-[A-Za-z0-9_-]+\.js)["'`]/g))queue.push('/frontend/'+match[1]);
}
if(!assets.size)throw new Error('Completed Angular asset graph is unavailable');
const ordered=[...assets.values()].sort((a,b)=>a.url.localeCompare(b.url));
const id=hash(JSON.stringify(ordered)).slice(0,16);
const sourceFiles=[];
function collect(directory){for(const entry of readdirSync(directory,{withFileTypes:true})){const path=resolve(directory,entry.name);if(entry.isDirectory())collect(path);else if(entry.isFile()&&!entry.name.endsWith('.spec.ts'))sourceFiles.push(path);}}
for(const directory of ['src','styles','assets','scripts'])collect(resolve(root,directory));
for(const name of ['package.json','package-lock.json','angular.json','tsconfig.json','tsconfig.app.json'])sourceFiles.push(resolve(root,name));
const sourceHash=createHash('sha256');
for(const path of sourceFiles.sort()){sourceHash.update(relative(root,path).replaceAll('\\','/')+'\0');sourceHash.update(readFileSync(path));}
html=html.replace(/<meta name="ouroboros-build" content="[^"]*">/g,'').replace('</head>',`<meta name="ouroboros-build" content="${id}"></head>`);
const manifest={version:1,build_id:id,created_at:new Date().toISOString(),source_sha256:sourceHash.digest('hex'),index_sha256:hash(html),assets:ordered};
function atomic(name,content){const destination=resolve(build,name),temporary=destination+'.delivery-tmp';try{writeFileSync(temporary,content,{encoding:'utf8'});renameSync(temporary,destination);}finally{try{unlinkSync(temporary);}catch(error){if(error.code!=='ENOENT')throw error;}}}
atomic('build-info.json',JSON.stringify(manifest,null,2)+'\n');
atomic('index.html',html);
process.stdout.write(`Frontend build ${id}: ${ordered.length} hashed assets, source fingerprint recorded\n`);

/** Generate the public constants from the backend-owned application policy. */
import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
const config=JSON.parse(readFileSync(new URL('../../app/text_limits.json',import.meta.url),'utf8'));
if(!Number.isSafeInteger(config.description_max_length)||config.description_max_length<1||config.grapheme_unicode_version!=='16.0.0')throw new Error('Invalid shared text limits or unsupported segmentation version');
const output='// Generated from app/text_limits.json; do not edit.\n'+
  `export const DESCRIPTION_MAX_LENGTH = ${config.description_max_length};\n`+
  `export const GRAPHEME_UNICODE_VERSION = ${JSON.stringify(config.grapheme_unicode_version)};\n`;
const target=new URL('../src/app/shared/text-limits.generated.ts',import.meta.url);
if(process.argv.includes('--check')){if(readFileSync(target,'utf8')!==output)throw new Error('Shared text limits are stale');}
else writeFileSync(fileURLToPath(target),output);

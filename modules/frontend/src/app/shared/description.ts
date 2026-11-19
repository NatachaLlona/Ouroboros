import { countGraphemes } from 'unicode-segmenter/grapheme';
import { DESCRIPTION_MAX_LENGTH } from './text-limits.generated';

export { DESCRIPTION_MAX_LENGTH } from './text-limits.generated';
export { countGraphemes as descriptionLength } from 'unicode-segmenter/grapheme';
export function descriptionError(value:string):string {
  return countGraphemes(value)>DESCRIPTION_MAX_LENGTH?'Use at most '+DESCRIPTION_MAX_LENGTH+' characters in the description.':'';
}

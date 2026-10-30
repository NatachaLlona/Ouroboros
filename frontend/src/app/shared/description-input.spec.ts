import { TestBed } from '@angular/core/testing';
import { splitGraphemes } from 'unicode-segmenter/grapheme';
import vectors from '../../../../qa/grapheme-vectors.json';
import { DescriptionInput } from './description-input';
import { DESCRIPTION_MAX_LENGTH, descriptionLength } from './description';
import { GRAPHEME_UNICODE_VERSION } from './text-limits.generated';

describe('Shared Unicode description limit',()=>{
  it('matches every official shared Unicode conformance boundary',()=>{
    expect(vectors.unicode_version).toBe(GRAPHEME_UNICODE_VERSION);
    for(const vector of vectors.cases){expect([...splitGraphemes(vector.text)]).toEqual(vector.segments);expect(descriptionLength(vector.text)).toBe(vector.segments.length);}
    for(const text of ['a',' ','e\u0301','👩🏽‍💻','👨‍👩‍👧‍👦','🇵🇹'])expect(descriptionLength(text)).toBe(1);
  });
  it('counts live input, rejects over-limit typing/paste as whole edits and preserves graphemes',()=>{
    const fixture=TestBed.createComponent(DescriptionInput);fixture.componentRef.setInput('fieldId','description_tags');fixture.detectChanges();const component=fixture.componentInstance,input=fixture.nativeElement.querySelector('textarea') as HTMLTextAreaElement;
    expect(input.hasAttribute('maxlength')).toBe(false);expect(input.required).toBe(false);
    input.value=' a e\u0301 👩🏽‍💻';input.dispatchEvent(new InputEvent('input'));fixture.detectChanges();expect(component.count()).toBe(descriptionLength(input.value));
    component.value.set('👨‍👩‍👧‍👦'.repeat(DESCRIPTION_MAX_LENGTH));fixture.detectChanges();input.setSelectionRange(input.value.length,input.value.length);
    const edit=new InputEvent('beforeinput',{data:'x',inputType:'insertText',cancelable:true});input.dispatchEvent(edit);expect(edit.defaultPrevented).toBe(true);expect(component.count()).toBe(DESCRIPTION_MAX_LENGTH);
    const paste=new Event('paste',{cancelable:true});Object.defineProperty(paste,'clipboardData',{value:{getData:()=> '🇵🇹'}});input.dispatchEvent(paste);expect(paste.defaultPrevented).toBe(true);
    input.value+='x';input.dispatchEvent(new InputEvent('input'));expect(input.value).toBe(component.value());expect(descriptionLength(input.value)).toBe(DESCRIPTION_MAX_LENGTH);
    input.setSelectionRange(0,input.value.length);const replace=new InputEvent('beforeinput',{data:'👩🏽‍💻',inputType:'insertText',cancelable:true});input.dispatchEvent(replace);expect(replace.defaultPrevented).toBe(false);input.value='👩🏽‍💻';input.dispatchEvent(new InputEvent('input'));fixture.detectChanges();expect(component.count()).toBe(1);
  });
  it('waits for composition to finish and never truncates historical oversized values',()=>{
    const fixture=TestBed.createComponent(DescriptionInput);fixture.componentRef.setInput('fieldId','description_tags');fixture.detectChanges();const component=fixture.componentInstance,input=fixture.nativeElement.querySelector('textarea') as HTMLTextAreaElement;
    component.value.set('x'.repeat(DESCRIPTION_MAX_LENGTH-1));fixture.detectChanges();input.dispatchEvent(new CompositionEvent('compositionstart'));input.value+='e\u0301';input.dispatchEvent(new InputEvent('input',{isComposing:true}));expect(component.value()).toHaveLength(DESCRIPTION_MAX_LENGTH-1);input.dispatchEvent(new CompositionEvent('compositionend'));expect(descriptionLength(component.value())).toBe(DESCRIPTION_MAX_LENGTH);
    input.dispatchEvent(new CompositionEvent('compositionstart'));input.value+='👩🏽‍💻';input.dispatchEvent(new InputEvent('input',{isComposing:true}));input.dispatchEvent(new CompositionEvent('compositionend'));expect(descriptionLength(input.value)).toBe(DESCRIPTION_MAX_LENGTH);
    const historical='x'.repeat(DESCRIPTION_MAX_LENGTH+2);component.value.set(historical);fixture.detectChanges();expect(input.value).toBe(historical);expect(component.overLimit()).toBe(true);input.value=input.value.slice(0,-1);input.dispatchEvent(new InputEvent('input'));expect(component.value().length).toBe(DESCRIPTION_MAX_LENGTH+1);component.value.set('');fixture.detectChanges();expect(component.count()).toBe(0);
  });
});

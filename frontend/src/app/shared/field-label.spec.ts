import { TestBed } from '@angular/core/testing';
import { FieldLabel, FANTASY_NAME_LABEL, FANTASY_NAME_HELP_TEXT } from './field-label';
import { SharedFormField } from './form-field';
import { resourceDefinitions } from '../catalogue/resources';
import { DESCRIPTION_MAX_LENGTH } from './description';

describe('Shared field labels and contextual help',()=>{
  it('uses exact centralized name text, a separated required marker and an associated non-submit help button',()=>{
    const fixture=TestBed.createComponent(FieldLabel);fixture.componentRef.setInput('fieldId','name');fixture.componentRef.setInput('label',FANTASY_NAME_LABEL);fixture.componentRef.setInput('help',FANTASY_NAME_HELP_TEXT);fixture.componentRef.setInput('required',true);fixture.detectChanges();
    const root=fixture.nativeElement as HTMLElement,button=root.querySelector('button')!,tooltip=root.querySelector('[role=tooltip]') as HTMLElement;
    expect(root.querySelector('label')?.textContent).toBe('* Nome Fantasia');expect(root.querySelector('label')?.htmlFor).toBe('name');expect(button.type).toBe('button');expect(button.getAttribute('aria-label')).toBe('Ajuda sobre Nome Fantasia');expect(button.getAttribute('aria-describedby')).toBe(tooltip.id);expect(tooltip.textContent).toBe('✨ Aqui você pode soltar a criatividade! Personalize com emojis, símbolos e pontuação, tudo do seu jeitinho. 💜');expect(tooltip.hidden).toBe(true);
    fixture.componentRef.setInput('required',false);fixture.detectChanges();expect(root.querySelector('.required-star')).toBeNull();
  });
  it('opens on hover, keyboard focus and touch-compatible click; closes on Escape and outside click',()=>{
    const fixture=TestBed.createComponent(FieldLabel);fixture.componentRef.setInput('fieldId','description');fixture.componentRef.setInput('label','Descrição');fixture.componentRef.setInput('help','Explique o significado desta tag.');fixture.detectChanges();
    const root=fixture.nativeElement as HTMLElement,row=root.querySelector('.label-row')!,button=root.querySelector('button')!,tip=root.querySelector('[role=tooltip]') as HTMLElement;
    row.dispatchEvent(new MouseEvent('mouseenter'));fixture.detectChanges();expect(tip.hidden).toBe(false);row.dispatchEvent(new MouseEvent('mouseleave'));fixture.detectChanges();expect(tip.hidden).toBe(true);
    button.focus();fixture.detectChanges();expect(tip.hidden).toBe(false);const escape=new KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true});button.dispatchEvent(escape);fixture.detectChanges();expect(escape.defaultPrevented).toBe(true);expect(tip.hidden).toBe(true);expect(document.activeElement).toBe(button);
    button.click();fixture.detectChanges();expect(tip.hidden).toBe(false);document.body.click();fixture.detectChanges();expect(tip.hidden).toBe(true);
  });
  it('removes description help while preserving visible errors and correct field associations',()=>{
    const fixture=TestBed.createComponent(SharedFormField);fixture.componentRef.setInput('error','Erro de validação');
    for(const resource of ['tags','work_classifications'] as const){fixture.componentRef.setInput('definition',resourceDefinitions[resource].fields[0]);fixture.detectChanges();const root=fixture.nativeElement as HTMLElement,key=resourceDefinitions[resource].fields[0].key;
      expect(root.querySelector('p.help')).toBeNull();expect(root.textContent).not.toContain('Opcional');expect(root.querySelector('[role=tooltip]')).toBeNull();expect(root.querySelector('.help-button')).toBeNull();expect(root.querySelector('textarea')?.getAttribute('aria-describedby')).toContain(key+'-error');expect(root.querySelector('.description-counter')?.textContent).toBe('0 / '+DESCRIPTION_MAX_LENGTH);expect(root.querySelector('.field-error')?.textContent).toBe('Erro de validação');
    }
  });
});

import { TestBed } from '@angular/core/testing';
import { MoneyInput } from './money-input';
import { TriState } from './tri-state';
import { SharedFormField } from './form-field';
import { priceDisplay, priceError, priceRecordText, priceValue } from './money';
import { editorPayload, emptyValues, recordValues, resourceDefinitions } from '../catalogue/resources';

describe('Shared registration controls and exact platform payloads',()=>{
  const definition=resourceDefinitions.platforms;
  const answered=()=>({...emptyValues(definition),platform_name:'Library',platform_is_paid:'false',platform_is_episodes:'true',platform_is_duration_time:'false'});
  it('starts booleans false and sends untouched checkboxes as valid booleans',()=>{
    expect(emptyValues(definition)).toMatchObject({platform_is_paid:'false',platform_is_episodes:'false',platform_is_duration_time:'false',price_amount:'',price_currency:'',platform_access_types:''});
    expect(editorPayload(definition,emptyValues(definition))).toMatchObject({platform_is_paid:false,platform_is_episodes:false,platform_is_duration_time:false});
    expect(editorPayload(definition,answered())).toMatchObject({platform_is_paid:false,platform_is_episodes:true,platform_is_duration_time:false});
  });
  it('uses a native mixed checkbox, distinguishable false and an explicit reset',()=>{
    const fixture=TestBed.createComponent(TriState);fixture.componentRef.setInput('fieldId','answer');fixture.componentRef.setInput('label','Plataforma paga');fixture.componentRef.setInput('required',true);fixture.detectChanges();
    const input=fixture.nativeElement.querySelector('input') as HTMLInputElement;
    expect(input.indeterminate).toBe(true);expect(input.getAttribute('aria-checked')).toBe('mixed');expect(input.getAttribute('aria-required')).toBe('true');
    input.click();fixture.detectChanges();expect(fixture.componentInstance.value()).toBe('true');expect(input.checked).toBe(true);
    input.click();fixture.detectChanges();expect(fixture.componentInstance.value()).toBe('false');expect(input.checked).toBe(false);expect(input.indeterminate).toBe(false);expect(fixture.nativeElement.textContent).toContain('Não');
    fixture.nativeElement.querySelector('button').click();fixture.detectChanges();expect(input.indeterminate).toBe(true);
  });
  it('separates unknown price, zero, comma parsing, exact precision and two-place display',()=>{
    expect(editorPayload(definition,answered())).not.toHaveProperty('price_amount');
    const priced={...editorPayload(definition,answered()),price_amount:'23.50'};
    expect(editorPayload(definition,{...recordValues(definition,priced),price_amount:''},priced)).toMatchObject({price_amount:null});
    expect(editorPayload(definition,recordValues(definition,priced),priced)).not.toHaveProperty('price_amount');
    expect(editorPayload(definition,{...answered(),platform_is_paid:'true',price_amount:'0'})['price_amount']).toBe('0');
    for(const [input,display,canonical] of [['10','10,00','10'],['10,5','10,50','10.5'],['10,50','10,50','10.50'],['23','23,00','23'],['23,5','23,50','23.5'],['23,50','23,50','23.50'],['0,00','0,00','0.00'],['23,555','23,56','23.555']]){
      expect(priceDisplay(input)).toBe(display);expect(priceValue(input)).toBe(canonical);
    }
    expect(priceDisplay('999999999999999999999999,995')).toBe('1000000000000000000000000,00');
    expect(priceRecordText('1.234E-8')).toBe('0,00000001234');expect(priceRecordText('1E+20')).toBe('100000000000000000000');
    for(const value of ['1.234','1.234,56','1,234.56','1 234,50','EUR 23','-1','NaN','Infinity'])expect(priceError(value)).not.toBe('');
    expect(priceError('-1')).toBe('Use um valor não negativo, sem símbolos nem separadores de milhar; use vírgula para os centavos.');
  });
  it('only formats on blur and preserves the exact editable value on focus',()=>{
    const fixture=TestBed.createComponent(MoneyInput);fixture.componentRef.setInput('fieldId','price');fixture.detectChanges();
    const input=fixture.nativeElement.querySelector('input') as HTMLInputElement;expect(input.value).toBe('');expect(input.placeholder).toBe('00,00');
    input.dispatchEvent(new FocusEvent('focus'));input.value='23,5';input.dispatchEvent(new Event('input'));fixture.detectChanges();expect(input.value).toBe('23,5');
    input.dispatchEvent(new FocusEvent('blur'));fixture.detectChanges();expect(input.value).toBe('23,50');expect(fixture.componentInstance.value()).toBe('23,5');
    input.dispatchEvent(new FocusEvent('focus'));fixture.detectChanges();expect(input.value).toBe('23,5');
  });
  it('offers exactly the configured currency codes and single application/website choices',()=>{
    const fixture=TestBed.createComponent(SharedFormField);fixture.componentRef.setInput('definition',definition.fields.find(field=>field.key==='price_currency'));fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('#price_currency').textContent).toContain('Selecione uma opção');expect(fixture.nativeElement.querySelector('.help')).toBeNull();
    fixture.componentInstance.value.set('BRL');fixture.detectChanges();expect(fixture.nativeElement.querySelector('#price_currency').textContent).toContain('BRL — Real brasileiro');expect(editorPayload(definition,{...answered(),platform_is_paid:'true',price_amount:'0',price_currency:fixture.componentInstance.value()})['price_currency']).toBe('BRL');
    let select:HTMLSelectElement;
    fixture.componentRef.setInput('definition',definition.fields.find(field=>field.key==='platform_access_types'));fixture.componentInstance.value.set('');fixture.detectChanges();
    select=fixture.nativeElement.querySelector('select');expect([...select.options].map(option=>[option.value,option.textContent])).toEqual([['','Selecione uma opção'],['application','Aplicativo'],['website','Site']]);expect(select.getAttribute('aria-required')).toBe('true');
    fixture.componentInstance.value.set('website,link');fixture.detectChanges();
    expect([...select.options].map(option=>option.value)).toEqual(['','application','website']);expect(fixture.componentInstance.value()).toBe('website,link');expect(select.options[0].disabled).toBe(true);expect(fixture.nativeElement.textContent).toContain('Não serão alterados');
  });
  it('omits hidden create URLs, clears persisted URLs on application selection, and preserves legacy arrays',()=>{
    expect(editorPayload(definition,{...answered(),platform_access_types:'application',platform_url:'https://example.org/draft'})).not.toHaveProperty('platform_url');
    expect(editorPayload(definition,{...answered(),platform_access_types:'website',platform_url:'https://example.org/draft'})).toMatchObject({platform_access_types:['website'],platform_url:'https://example.org/draft'});
    const original={platform_name:'Library',platform_is_paid:false,platform_is_episodes:true,platform_is_duration_time:false,price_amount:'23.12345',price_currency:'CAD',platform_access_types:['website','link'],platform_url:'https://example.org/current'};
    const values=recordValues(definition,original);
    expect(editorPayload(definition,{...values,platform_name:'Renamed'},original)).toEqual({platform_name:'Renamed'});
    expect(editorPayload(definition,{...values,platform_access_types:'application'},original)).toEqual({platform_access_types:['application'],platform_url:null});
  });
});

import { TestBed } from '@angular/core/testing';
import { Confirmation } from './confirmation';

describe('Cancel-first confirmation hierarchy and keyboard safety',()=>{
  const original=Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype,'showModal');
  beforeAll(()=>Object.defineProperty(HTMLDialogElement.prototype,'showModal',{configurable:true,value:function(this:HTMLDialogElement){this.open=true;}}));
  afterAll(()=>{if(original)Object.defineProperty(HTMLDialogElement.prototype,'showModal',original);else delete (HTMLDialogElement.prototype as any).showModal;});
  it('focuses and emphasizes Cancelar, with no implicit affirmative submission',async()=>{
    const fixture=TestBed.createComponent(Confirmation);fixture.componentRef.setInput('title','Apagar item?');fixture.componentRef.setInput('action','Apagar');const confirmed=vi.fn(),cancelled=vi.fn();fixture.componentInstance.confirmed.subscribe(confirmed);fixture.componentInstance.cancelled.subscribe(cancelled);await fixture.whenStable();fixture.detectChanges();
    const buttons=fixture.nativeElement.querySelectorAll('button') as NodeListOf<HTMLButtonElement>;
    expect(document.activeElement).toBe(buttons[0]);expect(buttons[0].textContent).toBe('Cancelar');expect(buttons[0].classList.contains('button-primary')).toBe(true);expect(buttons[1].classList.contains('button-primary')).toBe(false);expect(buttons[1].type).toBe('button');
    fixture.nativeElement.querySelector('dialog').dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));expect(confirmed).not.toHaveBeenCalled();buttons[0].click();expect(cancelled).toHaveBeenCalledTimes(1);expect(confirmed).not.toHaveBeenCalled();
    buttons[1].click();expect(confirmed).toHaveBeenCalledTimes(1);
  });
  it('Escape cancels only outside an in-flight confirmed operation',async()=>{
    const fixture=TestBed.createComponent(Confirmation);fixture.componentRef.setInput('title','Editar existente?');const cancelled=vi.fn();fixture.componentInstance.cancelled.subscribe(cancelled);await fixture.whenStable();
    const event=new Event('cancel',{cancelable:true});fixture.componentInstance.cancel(event);expect(event.defaultPrevented).toBe(true);expect(cancelled).toHaveBeenCalledTimes(1);
    fixture.componentRef.setInput('busy',true);fixture.componentInstance.cancel(new Event('cancel',{cancelable:true}));expect(cancelled).toHaveBeenCalledTimes(1);
  });
});

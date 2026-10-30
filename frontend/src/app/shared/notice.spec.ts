import { TestBed } from '@angular/core/testing';
import { Notice } from './notice';
describe('Visible repeated feedback', () => {
  it('focuses and reveals the same message again for a new action', async () => {
    const scroll = vi.fn();
    HTMLElement.prototype.scrollIntoView = scroll;
    await TestBed.configureTestingModule({imports:[Notice]}).compileComponents();
    const fixture=TestBed.createComponent(Notice);
    fixture.componentRef.setInput('text','Acesso recusado.');
    fixture.detectChanges(); await fixture.whenStable();
    const message=fixture.nativeElement.querySelector('[role=status]') as HTMLElement;
    expect(document.activeElement).toBe(message); expect(scroll).toHaveBeenCalledTimes(1);
    message.blur();
    fixture.componentRef.setInput('activation',1);
    fixture.detectChanges(); await fixture.whenStable();
    expect(document.activeElement).toBe(message); expect(scroll).toHaveBeenCalledTimes(2);
  });
});

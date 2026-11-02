import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideHttpClient,withNoXsrfProtection } from '@angular/common/http';
import { provideHttpClientTesting,HttpTestingController } from '@angular/common/http/testing';
import { signal } from '@angular/core';
import { Registration } from './registration';
import { Session } from '../auth/session';

describe('Category registration through the real frontend HTTP boundary',()=>{
  it('sends category creation through Api and preserves the draft on a subsequent HTTP failure',async()=>{
    const state={authenticated:true,can_create:true,csrf_token:'test-csrf'};
    await TestBed.configureTestingModule({imports:[Registration],providers:[provideRouter([]),provideHttpClient(withNoXsrfProtection()),provideHttpClientTesting(),{provide:Session,useValue:{current:signal(state),canCreate:signal(true),ensure:async()=>state}}]}).compileComponents();
    const fixture=TestBed.createComponent(Registration),component=fixture.componentInstance,http=TestBed.inject(HttpTestingController);await fixture.whenStable();await component.choose('tag_categories');await fixture.whenStable();
    expect(fixture.nativeElement.querySelector('label[for=description_tag_categories]')?.textContent).toBe('Descrição');
    component.setValue('display_name_tag_categories','Category');component.setValue('description_tag_categories','Description');
    const first=component.submit(new Event('submit'));await component.submit(new Event('submit'));
    const request=http.expectOne('/tag_categories');expect(request.request.method).toBe('POST');expect(request.request.headers.get('X-CSRF-Token')).toBe('test-csrf');expect(request.request.body).toEqual({tag_category_name:'category',display_name_tag_categories:'Category',description_tag_categories:'Description'});
    request.flush({id_tag_categories:'TC0000001',display_name_tag_categories:'Category'});await first;expect(component.success()?.id).toBe('TC0000001');
    component.another();component.setValue('display_name_tag_categories','Retained');const second=component.submit(new Event('submit'));
    http.expectOne('/tag_categories').flush({error:{code:'VALIDATION_ERROR'}},{status:422,statusText:'Unprocessable Entity'});await second;await fixture.whenStable();expect(component.values()['display_name_tag_categories']).toBe('Retained');expect(fixture.nativeElement.querySelector('.form-error')).not.toBeNull();http.verify();
  });
});

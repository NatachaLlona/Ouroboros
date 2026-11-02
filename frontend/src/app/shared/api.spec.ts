import { TestBed } from '@angular/core/testing';
import { provideHttpClient, withNoXsrfProtection } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { Api, ApiError, safeMessage } from './api';
describe('Same-origin API boundary', () => {
  beforeEach(()=>TestBed.configureTestingModule({providers:[provideHttpClient(withNoXsrfProtection()),provideHttpClientTesting()]}));
  afterEach(()=>TestBed.inject(HttpTestingController).verify());
  it('sends the exact synchronizer CSRF header, never bearer credentials', async () => {
    const request=TestBed.inject(Api).request('/tags','POST',{tag_name:'test'},'test-csrf');
    const pending=TestBed.inject(HttpTestingController).expectOne('/tags');
    expect(pending.request.headers.get('X-CSRF-Token')).toBe('test-csrf');
    expect(pending.request.headers.has('Authorization')).toBe(false);
    pending.flush({id_tags:'TG0000001'}); await request;
  });
  it('rejects external/unapproved endpoints before any request', async () => {
    await expect(TestBed.inject(Api).request('https://untrusted.example')).rejects.toBeInstanceOf(ApiError);
    TestBed.inject(HttpTestingController).expectNone('https://untrusted.example');
  });
  it('permits category creation with existing CSRF handling without enabling category consultation or relationships',async()=>{
    const api=TestBed.inject(Api),http=TestBed.inject(HttpTestingController);
    const body={tag_category_name:'category',display_name_tag_categories:'Category',description_tag_categories:null};
    const created=api.request('/tag_categories','POST',body,'test-csrf');const pending=http.expectOne('/tag_categories');
    expect(pending.request.method).toBe('POST');expect(pending.request.body).toEqual(body);expect(pending.request.headers.get('X-CSRF-Token')).toBe('test-csrf');expect(pending.request.headers.has('Authorization')).toBe(false);
    pending.flush({id_tag_categories:'TC0000001'});await created;
    for(const [path,method] of [['/tag_categories','GET'],['/tag_categories/TC0000001','PUT'],['/tag_relationships','POST'],['/tag_category_relationships','POST']])await expect(api.request(path,method)).rejects.toBeInstanceOf(ApiError);
    http.expectNone('/tag_categories');
  });
  it('separates configuration, permissions, invalid credentials, expiry and unknown commit status', () => {
    expect(safeMessage(new ApiError(403,'BROWSER_ORIGIN_REJECTED'))).toContain('browser.origin');
    expect(safeMessage(new ApiError(403,'INSUFFICIENT_PERMISSIONS'))).toContain('supervisor');
    expect(safeMessage(new ApiError(401,'INVALID_CREDENTIALS'))).toContain('inválidos');
    expect(safeMessage(new ApiError(401,'INVALID_TOKEN'))).toContain('sessão terminou');
    expect(safeMessage(new ApiError(0,'',[],'','','/tags','POST'))).toContain('Confirme se o registo');
  });
});

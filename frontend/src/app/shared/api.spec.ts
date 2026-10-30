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
  it('separates configuration, permissions, invalid credentials, expiry and unknown commit status', () => {
    expect(safeMessage(new ApiError(403,'BROWSER_ORIGIN_REJECTED'))).toContain('browser.origin');
    expect(safeMessage(new ApiError(403,'INSUFFICIENT_PERMISSIONS'))).toContain('supervisor');
    expect(safeMessage(new ApiError(401,'INVALID_CREDENTIALS'))).toContain('inválidos');
    expect(safeMessage(new ApiError(401,'INVALID_TOKEN'))).toContain('sessão terminou');
    expect(safeMessage(new ApiError(0,'',[],'','','/tags','POST'))).toContain('Confirme se o registo');
  });
});

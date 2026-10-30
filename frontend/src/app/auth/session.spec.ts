import { TestBed } from '@angular/core/testing';
import { Session } from './session';
import { Api, ApiError } from '../shared/api';
describe('In-memory absolute browser session', () => {
  const api = { request: vi.fn() };
  const state = { authenticated:true, username:'supervisor', role:'supervisor', is_active:true, can_create:true, csrf_token:'test-csrf', expires_in:60 };
  beforeEach(()=>{ vi.useFakeTimers(); vi.clearAllMocks(); TestBed.configureTestingModule({providers:[{provide:Api,useValue:api}]}); });
  afterEach(()=>vi.useRealTimers());
  it('coalesces reload requests and expires without extending on navigation', async () => {
    api.request.mockResolvedValueOnce(state).mockResolvedValue({authenticated:false}); const session=TestBed.inject(Session);
    await Promise.all([session.ensure(),session.ensure()]); await session.ensure();
    expect(api.request).toHaveBeenCalledTimes(1); expect(session.canCreate()).toBe(true);
    await vi.advanceTimersByTimeAsync(60000);
    expect(session.current().authenticated).toBe(false); expect(session.loginOpen()).toBe(true);
  });
  it('uses current public permission metadata and clears state after CSRF logout', async () => {
    api.request.mockResolvedValueOnce({...state,role:'standard',can_create:false}).mockResolvedValueOnce(null);
    const session=TestBed.inject(Session); await session.ensure(); expect(session.canCreate()).toBe(false);
    await session.logout(); expect(api.request).toHaveBeenLastCalledWith('/browser/logout','POST',undefined,'test-csrf'); expect(session.current().authenticated).toBe(false);
  });
  it('rejects malformed server state as a server error rather than permissions', async () => {
    api.request.mockResolvedValue({authenticated:true});
    await expect(TestBed.inject(Session).ensure()).rejects.toMatchObject({status:502});
    expect(TestBed.inject(Session).canCreate()).toBe(false);
  });
});

import { TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';
import { Router, provideRouter } from '@angular/router';
import { Login } from './login';
import { Session } from './session';
import { ApiError } from '../shared/api';
describe('Login security and error feedback', () => {
  const session={login:vi.fn(),loginReason:signal('Entre para continuar.'),loginOpen:signal(true),returnUrl:signal('/cadastros')};
  beforeEach(async()=>{
    vi.clearAllMocks(); vi.useFakeTimers(); session.loginOpen.set(true); session.returnUrl.set('/cadastros');
    await TestBed.configureTestingModule({imports:[Login],providers:[provideRouter([]),{provide:Session,useValue:session}]}).compileComponents();
  });
  afterEach(()=>vi.useRealTimers());
  it('clears password while pending and never automatically retries a failed login',async()=>{
    const component=TestBed.createComponent(Login).componentInstance;
    component.model.set({username:'supervisor',password:'Disposable QA passphrase'});
    let reject!: (error:unknown)=>void; session.login.mockReturnValue(new Promise((_,fail)=>reject=fail));
    const pending=component.submit(new Event('submit'));
    expect(component.model().password).toBe(''); await component.submit(new Event('submit')); expect(session.login).toHaveBeenCalledTimes(1);
    reject(new ApiError(401,'INVALID_CREDENTIALS')); await pending;
    expect(component.error()).toContain('inválidos'); expect(component.busy()).toBe(false);
  });
  it('honors Retry-After with visible countdown and no retained password',async()=>{
    const component=TestBed.createComponent(Login).componentInstance;
    component.model.set({username:'supervisor',password:'Disposable QA passphrase'});
    session.login.mockRejectedValue(new ApiError(429,'LOGIN_THROTTLED',[],'','3'));
    await component.submit(new Event('submit')); expect(component.remaining()).toBe(3); expect(component.model().password).toBe('');
    component.model.update(value=>({...value,password:'Another disposable passphrase'}));
    await component.submit(new Event('submit')); expect(session.login).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(3000); expect(component.remaining()).toBe(0);
  });
  it('reauthenticates in place without navigating away from a draft',async()=>{
    const router=TestBed.inject(Router); Object.defineProperty(router,'url',{get:()=>'/cadastros'});
    const navigate=vi.spyOn(router,'navigateByUrl');session.login.mockResolvedValue(undefined);
    const component=TestBed.createComponent(Login).componentInstance;component.model.set({username:'supervisor',password:'Disposable QA passphrase'});
    await component.submit(new Event('submit'));expect(navigate).not.toHaveBeenCalled();expect(session.loginOpen()).toBe(false);expect(component.model().password).toBe('');
  });
  it('returns to the requested consultation after login',async()=>{
    const router=TestBed.inject(Router); const navigate=vi.spyOn(router,'navigateByUrl').mockResolvedValue(true);
    session.returnUrl.set('/consultas'); session.login.mockResolvedValue(undefined);
    const component=TestBed.createComponent(Login).componentInstance;
    component.model.set({username:'supervisor',password:'Disposable QA passphrase'});
    await component.submit(new Event('submit'));
    expect(navigate).toHaveBeenCalledWith('/consultas'); expect(component.model().password).toBe('');
  });
});

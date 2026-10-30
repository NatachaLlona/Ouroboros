import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { App } from './app';
import { Session } from './auth/session';
import { UnsavedChanges } from './shared/unsaved-changes';

describe('Logout respects unsaved-change cancellation',()=>{
  const session={current:signal({authenticated:true,username:'user'}),loginOpen:signal(false),logout:vi.fn()};
  beforeEach(()=>{session.logout.mockReset().mockResolvedValue(undefined);TestBed.configureTestingModule({imports:[App],providers:[provideRouter([]),{provide:Session,useValue:session}]});});
  it('identifies the build loaded by this document rather than a later server build',()=>{
    const meta=document.createElement('meta');meta.name='ouroboros-build';meta.content='0123456789abcdef';document.head.append(meta);
    try{const app=TestBed.createComponent(App).componentInstance;expect(app.buildId).toBe('0123456789abcdef');meta.content='fedcba9876543210';expect(app.buildId).toBe('0123456789abcdef');}finally{meta.remove();}
  });
  it('keeps the session and page when discard is cancelled',async()=>{
    const app=TestBed.createComponent(App).componentInstance,unsaved=TestBed.inject(UnsavedChanges),navigate=vi.spyOn(TestBed.inject(Router),'navigateByUrl').mockResolvedValue(true);unsaved.register(()=>unsaved.ask());
    const pending=app.logout();expect(unsaved.asking()).toBe(true);expect(session.logout).not.toHaveBeenCalled();unsaved.decide(false);await pending;
    expect(session.logout).not.toHaveBeenCalled();expect(navigate).not.toHaveBeenCalled();expect(app.busy()).toBe(false);
  });
  it('allows only one logout after explicit discard confirmation',async()=>{
    const app=TestBed.createComponent(App).componentInstance,unsaved=TestBed.inject(UnsavedChanges),navigate=vi.spyOn(TestBed.inject(Router),'navigateByUrl').mockResolvedValue(true);unsaved.register(()=>unsaved.ask());
    const pending=app.logout();await app.logout();unsaved.decide(true);await pending;
    expect(session.logout).toHaveBeenCalledTimes(1);expect(navigate).toHaveBeenCalledWith('/');expect(app.busy()).toBe(false);
  });
});

import { DestroyRef, Injectable, computed, inject, signal } from '@angular/core';
import { Api, ApiError } from '../shared/api';
export interface SessionState { authenticated: boolean; username?: string; role?: string; is_active?: boolean; can_create?: boolean; csrf_token?: string; expires_in?: number; absolute_expires_in?:number; }
@Injectable({ providedIn: 'root' })
export class Session {
  private readonly api = inject(Api);
  private readonly state = signal<SessionState>({ authenticated: false });
  readonly current = this.state.asReadonly();
  readonly canCreate = computed(() => this.state().authenticated && this.state().can_create === true);
  readonly loginOpen = signal(false);
  readonly loginReason = signal('');
  readonly returnUrl=signal('/cadastros');
  readonly generation=signal(0);
  private loaded = false;
  private loading?: Promise<SessionState>;
  private expiry?: ReturnType<typeof setTimeout>;
  constructor() {
    const subscription=this.api.deadlines?.subscribe(value=>{if(this.state().authenticated)this.remember({...this.state(),expires_in:value.idle,absolute_expires_in:value.absolute});});
    inject(DestroyRef).onDestroy(() => {clearTimeout(this.expiry);subscription?.unsubscribe();});
  }
  private remember(value: SessionState): SessionState {
    if (!value || typeof value.authenticated !== 'boolean' || (value.authenticated &&
      (typeof value.username !== 'string' || typeof value.can_create !== 'boolean' || typeof value.csrf_token !== 'string' || !Number.isFinite(value.expires_in)))) throw new ApiError(502);
    if(this.state().authenticated&&!value.authenticated)this.generation.update(value=>value+1);
    clearTimeout(this.expiry); this.state.set(value); this.loaded = true;
    if (value.authenticated) this.expiry = setTimeout(() => {void this.ensure(true).then(state=>{if(!state.authenticated)this.expire();}).catch(()=>this.expire());}, Math.max(1, value.expires_in!) * 1000);
    return value;
  }
  ensure(force = false): Promise<SessionState> {
    if (this.loading) return this.loading;
    if (this.loaded && !force) return Promise.resolve(this.state());
    this.loading = this.api.request<SessionState>('/browser/session').then(value => this.remember(value)).finally(() => this.loading = undefined);
    return this.loading;
  }
  async login(username: string, password: string): Promise<void> {
    this.remember(await this.api.request<SessionState>('/browser/login', 'POST', { username, password }));
    this.generation.update(value=>value+1);
  }
  async logout(): Promise<void> {
    await this.api.request('/browser/logout', 'POST', undefined, this.state().csrf_token);
    this.remember({ authenticated: false });
  }
  openLogin(reason = 'Entre para continuar.',destination?:string): void { if(destination && ['/cadastros','/consultas'].includes(destination))this.returnUrl.set(destination);this.loginReason.set(reason); this.loginOpen.set(true); }
  expire(): void { this.remember({ authenticated: false }); this.openLogin('A sua sessão terminou. Entre novamente; os valores continuam aqui.'); }
}

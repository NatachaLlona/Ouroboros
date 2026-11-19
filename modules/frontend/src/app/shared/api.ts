import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpErrorResponse, HttpHeaders } from '@angular/common/http';
import { firstValueFrom, timeout, Subject, takeUntil, fromEvent, EMPTY } from 'rxjs';

export interface ValidationDetail { loc?: (string | number)[]; }
export class ApiError extends Error {
  constructor(readonly status: number, readonly code = '', readonly details: ValidationDetail[] = [],
    readonly interaction = '', readonly retryAfter = '', readonly path = '', readonly method = 'GET') {
    super('Request could not be completed');
  }
}
@Injectable({ providedIn: 'root' })
export class Api {
  private readonly http = inject(HttpClient);
  readonly deadlines = new Subject<{idle:number;absolute:number}>();
  async request<T>(path: string, method = 'GET', body?: unknown, csrf?: string, params:Record<string,string|number>={}, userActivity=true, abortSignal?:AbortSignal, requestTimeoutMs?:number): Promise<T> {
    const transcription=path==='/browser/transcription'&&method==='POST';
    const assistant=path==='/browser/assistant/work-classifications'&&method==='POST';
    const speechOptions=path==='/browser/transcription/options'&&method==='GET';
    const categoryAccess=path==='/tag_categories'&&(method==='GET'||method==='POST');
    const categoryRecord=/^\/tag_categories\/[A-Za-z0-9]+$/.test(path)&&['GET','PUT','DELETE'].includes(method);
    const categoryLinks=path==='/tag_category_relationships'&&(method==='GET'||method==='POST')||/^\/tag_category_relationships\/[A-Za-z0-9]+$/.test(path)&&method==='DELETE';
    if (abortSignal?.aborted||(!assistant&&!speechOptions&&!transcription&&!categoryAccess&&!categoryRecord&&!categoryLinks&&!/^\/(?:browser\/(?:session|login|logout)|(?:platforms|tags|work_classifications)(?:\/[A-Za-z0-9]+)?)$/.test(path)) || !['GET','POST','PUT','DELETE'].includes(method)) throw new ApiError(400);
    let headers = new HttpHeaders({ Accept: 'application/json' });
    if (body !== undefined) headers = headers.set('Content-Type', transcription&&body instanceof Blob?body.type:'application/json');
    if (csrf) headers = headers.set('X-CSRF-Token', csrf);
    if (userActivity && !path.startsWith('/browser/')) headers=headers.set('X-Ouroboros-Activity','user');
    try {
      const response = await firstValueFrom(this.http.request<T>(method, path, { body, headers, params, observe: 'response' }).pipe(timeout(requestTimeoutMs??(assistant?90000:30000)),takeUntil(abortSignal?fromEvent(abortSignal,'abort'):EMPTY)));
      const idleHeader=response.headers.get('X-Browser-Expires-In'),absoluteHeader=response.headers.get('X-Browser-Absolute-Expires-In');
      if(idleHeader!==null && absoluteHeader!==null){const idle=Number(idleHeader),absolute=Number(absoluteHeader);if(Number.isFinite(idle)&&Number.isFinite(absolute)&&idle>=0&&idle<=absolute&&absolute<=86400)this.deadlines.next({idle,absolute});}
      if (response.status !== 204 && response.body === null) throw new ApiError(502, '', [], response.headers.get('X-Interaction-ID') || '', '', path, method);
      return response.body as T;
    } catch (error) {
      if (error instanceof ApiError) throw error;
      if (error instanceof HttpErrorResponse) {
        const envelope = error.error?.error;
        throw new ApiError(error.status === 200 ? 502 : error.status, typeof envelope?.code==='string'?envelope.code:'', Array.isArray(envelope?.details)?envelope.details:[],
          error.headers.get('X-Interaction-ID') || '', error.headers.get('Retry-After') || '', path, method);
      }
      throw new ApiError(0, '', [], '', '', path, method);
    }
  }
}
export function safeMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return 'Could not complete the request. Try again later.';
  const speechMessages:Record<string,string>={
    ASSISTANT_UNAVAILABLE:'The assistant is unavailable. Check the backend configuration or try again.',
    ASSISTANT_BUSY:'The assistant is busy. Wait and try again.',
    ASSISTANT_RATE_LIMITED:'The OpenAI project reached a usage or request limit. Check the account balance and limits.',
    ASSISTANT_UPSTREAM_REJECTED:'The gpt-5.4 model could not complete the request. Check model access and try again.',
    ASSISTANT_INVALID_OUTPUT:'The suggestion failed validation. Your fields are preserved.',
    AUDIO_INVALID:'The audio is empty, unsupported or contains no recognizable speech.',
    AUDIO_LIMIT_EXCEEDED:'The audio exceeds the server size or duration limit.',
    TRANSCRIPTION_BUSY:'Local transcription is busy. Wait and try again.',
    TRANSCRIPTION_UNAVAILABLE:'Local transcription is unavailable. Check the server dependencies and model cache.',
    TRANSCRIPTION_LANGUAGE_REJECTED:'The detected language is not allowed by the server configuration.',
    TRANSCRIPTION_TIMEOUT:'Transcription exceeded the configured processing time. No partial text was inserted.'
  };
  if(speechMessages[error.code])return speechMessages[error.code];
  const mutation = error.method !== 'GET' && !error.path.startsWith('/browser/');
  const messages: Record<number, string> = {
    0: mutation ? 'Could not confirm the response. Check whether the record was created before submitting again.' : 'Could not reach the service. Check your connection and try again.',
    401: error.code === 'INVALID_CREDENTIALS' ? 'Invalid App User username or App Password.' : 'Your session expired. Sign in again; your form values are preserved.',
    403: error.code === 'BROWSER_ORIGIN_REJECTED' ? 'The browser address or connection does not match this installation. Check browser.origin and the explicit browser.allow_loopback_http setting for local HTTP; restart the application. This rejection does not indicate missing account permissions.' : error.code === 'CSRF_REJECTED' ? 'Session verification needs refreshing. Review your data before submitting again.' : 'This area requires catalogue permissions: supervisor or administrator. Contact an administrator.',
    409: error.method==='DELETE' ? 'Cannot delete this item: other records depend on it. Resolve those dependencies before trying again.' : 'This entry conflicts with an existing record. Review the data.',
    422: 'Review the highlighted fields and try again.',
    429: 'Too many sign-in attempts. Wait before trying again.',
    500: 'A server error occurred. Try again later.',
    502: 'The service returned an invalid response. Try again later.',
    503: 'The service is temporarily unavailable. Your entered values are preserved.'
  };
  return (messages[error.status] || 'Could not complete the request.') + (error.interaction && /^\d{24}$/.test(error.interaction) ? ` Reference: ${error.interaction}` : '');
}

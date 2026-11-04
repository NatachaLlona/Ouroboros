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
  if (!(error instanceof ApiError)) return 'Não foi possível concluir o pedido. Tente novamente mais tarde.';
  const speechMessages:Record<string,string>={
    ASSISTANT_UNAVAILABLE:'A assistente está indisponível. Verifique a configuração do backend ou tente novamente.',
    ASSISTANT_BUSY:'A assistente está ocupada. Aguarde e tente novamente.',
    ASSISTANT_RATE_LIMITED:'O projeto OpenAI atingiu um limite de uso ou requisições. Verifique o saldo e os limites da conta.',
    ASSISTANT_UPSTREAM_REJECTED:'O modelo gpt-5.4 não conseguiu concluir o pedido. Verifique o acesso ao modelo e tente novamente.',
    ASSISTANT_INVALID_OUTPUT:'A sugestão recebida não passou pela validação. Os campos foram preservados.',
    AUDIO_INVALID:'O áudio está vazio, não é suportado ou não contém fala reconhecível.',
    AUDIO_LIMIT_EXCEEDED:'O áudio excede o limite de tamanho ou duração configurado no servidor.',
    TRANSCRIPTION_BUSY:'A transcrição local está ocupada. Aguarde e tente novamente.',
    TRANSCRIPTION_UNAVAILABLE:'A transcrição local está indisponível. Verifique as dependências e o cache do modelo no servidor.',
    TRANSCRIPTION_LANGUAGE_REJECTED:'O idioma detectado não está permitido na configuração do servidor.',
    TRANSCRIPTION_TIMEOUT:'A transcrição excedeu o tempo de processamento configurado. Nenhum texto parcial foi inserido.'
  };
  if(speechMessages[error.code])return speechMessages[error.code];
  const mutation = error.method !== 'GET' && !error.path.startsWith('/browser/');
  const messages: Record<number, string> = {
    0: mutation ? 'Não foi possível confirmar a resposta. Confirme se o registo foi criado antes de reenviar.' : 'Não foi possível comunicar com o serviço. Verifique a ligação e tente novamente.',
    401: error.code === 'INVALID_CREDENTIALS' ? 'Nome de utilizador ou palavra-passe inválidos.' : 'A sua sessão terminou. Entre novamente; os valores do formulário continuam aqui.',
    403: error.code === 'BROWSER_ORIGIN_REJECTED' ? 'O endereço ou a ligação do navegador não corresponde à configuração desta instalação. Verifique browser.origin e a opção explícita browser.allow_loopback_http para HTTP local; reinicie a aplicação. Esta rejeição não indica falta de permissões da conta.' : error.code === 'CSRF_REJECTED' ? 'A verificação da sessão precisa de ser atualizada. Reveja os dados antes de reenviar.' : 'Esta área requer permissões de catálogo: supervisor ou administrador. Contacte um administrador.',
    409: error.method==='DELETE' ? 'Não é possível apagar este item: existem registos que dependem dele. Resolva essas dependências antes de tentar novamente.' : 'Este cadastro entra em conflito com um registo existente. Reveja os dados.',
    422: 'Reveja os campos indicados e tente novamente.',
    429: 'Várias tentativas de entrada. Aguarde antes de tentar novamente.',
    500: 'Ocorreu um erro no servidor. Tente novamente mais tarde.',
    502: 'O serviço devolveu uma resposta inválida. Tente novamente mais tarde.',
    503: 'O serviço está temporariamente indisponível. Os valores introduzidos foram preservados.'
  };
  return (messages[error.status] || 'Não foi possível concluir o pedido.') + (error.interaction && /^\d{24}$/.test(error.interaction) ? ` Referência: ${error.interaction}` : '');
}

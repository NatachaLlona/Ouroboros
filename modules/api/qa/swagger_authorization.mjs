/** Exercise the real Swagger bundle and plugin with synthetic HTTP responses. */
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';

const require = createRequire(new URL('../../frontend/package.json', import.meta.url));
const { JSDOM } = require('jsdom');
const dom = new JSDOM('<!doctype html><div id="swagger-ui"></div>', {
  url: 'https://localhost:6969/docs', runScripts: 'outside-only', pretendToBeVisual: true
});
const { window } = dom;
const calls = [];
window.matchMedia = () => ({ matches: false, addListener() {}, removeListener() {} });
window.scrollTo = () => {};
window.Headers = Headers;
window.Request = Request;
window.Response = Response;
window.TextEncoder = TextEncoder;
window.TextDecoder = TextDecoder;
window.fetch = async (input, options = {}) => {
  const url = new URL(typeof input === 'string' ? input : input.url, window.location.origin);
  const headers = new Headers(options.headers || input.headers);
  calls.push({path: url.pathname, authorization: headers.get('Authorization')});
  let status = 200;
  let payload;
  if (url.pathname === '/auth/user-token') {
    const body = JSON.parse(options.body);
    if (['app-login', 'linked-api-login'].includes(body.username) && body.password === 'synthetic-app-password') {
      payload = {access_token: 'synthetic-human-token', token_type: 'bearer'};
    } else {
      status = 401;
      payload = {error: {message: 'Invalid authentication credentials'}};
    }
  } else if (url.pathname === '/oauth/token') {
    const body = new URLSearchParams(options.body.toString());
    if (body.get('client_id') === 'synthetic-client-id' && body.get('client_secret') === 'synthetic-client-secret') {
      payload = {access_token: 'synthetic-integration-token', token_type: 'bearer', scope: 'test:read'};
    } else {
      status = 401;
      payload = {error: {message: 'Invalid authentication credentials'}};
    }
  } else if (url.pathname === '/me') {
    payload = {kind: 'human_password', id_api_user: 'synthetic-human'};
  } else if (url.pathname === '/test') {
    payload = {items: [], total: 0};
  } else {
    throw new Error('Unexpected Swagger DOM test request');
  }
  return new Response(JSON.stringify(payload), {status, headers: {'Content-Type': 'application/json'}});
};

window.eval(readFileSync(new URL('../service/swagger/vendor/swagger-ui-bundle.js', import.meta.url), 'utf8'));
window.eval(readFileSync(new URL('../service/swagger/authorize.js', import.meta.url), 'utf8'));
const ui = window.SwaggerUIBundle({
  dom_id: '#swagger-ui', persistAuthorization: false, plugins: [window.OuroborosAuthPlugin],
  spec: {
    openapi: '3.0.3', info: {title: 'Synthetic Swagger QA', version: '1'},
    servers: [{url: window.location.origin}],
    components: {securitySchemes: {
      HumanBearer: {type: 'http', scheme: 'bearer'},
      OAuth2: {type: 'oauth2', flows: {clientCredentials: {tokenUrl: '/oauth/token', scopes: {}}}}
    }},
    paths: {'/test': {get: {
      operationId: 'protectedRead', security: [{HumanBearer: []}, {OAuth2: []}],
      responses: {'200': {description: 'Successful protected read'}}
    }}}
  }
});

async function until(condition) {
  const deadline = Date.now() + 10000;
  while (!condition()) {
    if (Date.now() > deadline) throw new Error('Swagger DOM interaction timed out');
    await new Promise(resolve => setTimeout(resolve, 20));
  }
}

function fill(id, value) {
  const input = window.document.getElementById(id);
  if (!input) throw new Error('Expected authorization input is missing');
  Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set.call(input, value);
  input.dispatchEvent(new window.Event('input', {bubbles: true}));
}

function click(text) {
  const button = [...window.document.querySelectorAll('button')].find(item => item.textContent.trim() === text);
  if (!button) throw new Error('Expected Swagger action is missing: ' + text);
  button.click();
}

async function openAuthorization() {
  click('Authorize');
  await until(() => window.document.getElementById('app-login'));
  const labels = [...window.document.querySelectorAll('.ouroboros-auth label')].map(item => item.textContent);
  if (labels.join('|') !== 'App User or linked API User|App Password|Human Access Token|Client ID|Client Secret') {
    throw new Error('Swagger authorization labels are incorrect');
  }
}

async function protectedRead(expected) {
  click('Close');
  await until(() => !window.document.querySelector('.ouroboros-auth'));
  if (!window.document.querySelector('.opblock.is-open')) {
    window.document.querySelector('.opblock-summary-control').click();
    await until(() => window.document.querySelector('.try-out__btn'));
    click('Try it out');
  }
  await until(() => window.document.querySelector('.execute'));
  const before = calls.filter(item => item.path === '/test').length;
  click('Execute');
  await until(() => calls.filter(item => item.path === '/test').length > before);
  await until(() => window.document.querySelector('.execute')?.disabled === false);
  click('Execute');
  await until(() => calls.filter(item => item.path === '/test').length > before + 1);
  const last = calls.filter(item => item.path === '/test').slice(-2);
  if (!last.every(item => item.authorization === 'Bearer ' + expected)) {
    throw new Error('Protected requests did not reuse the selected authorization');
  }
}

try {
  await until(() => window.document.querySelector('.auth-wrapper button'));
  for (const name of ['app-login', 'linked-api-login']) {
    await openAuthorization();
    fill('app-login', name);
    fill('app-password', 'synthetic-app-password');
    click('Sign in and authorize');
    await until(() => window.document.querySelector('[role="status"]')?.textContent.includes('Authorized.'));
    if (window.document.getElementById('app-password').value) throw new Error('App Password remained in the form');
    await protectedRead('synthetic-human-token');
  }
  await openAuthorization();
  fill('app-login', 'app-login');
  fill('app-password', 'incorrect-synthetic-password');
  click('Sign in and authorize');
  await until(() => window.document.querySelector('[role="status"]')?.textContent.includes('Invalid authentication credentials'));
  if (ui.authSelectors.authorized().size) throw new Error('Failed sign-in retained an authorization');
  fill('human-token', 'synthetic-human-token');
  click('Use human access token');
  await until(() => ui.authSelectors.authorized().has('HumanBearer'));
  await protectedRead('synthetic-human-token');
  await openAuthorization();
  fill('client-id', 'synthetic-client-id');
  fill('client-secret', 'synthetic-client-secret');
  click('Authorize integration');
  await until(() => ui.authSelectors.authorized().has('OAuth2'));
  if (window.document.getElementById('client-secret').value) throw new Error('Client Secret remained in the form');
  await protectedRead('synthetic-integration-token');
  if (window.localStorage.length || window.sessionStorage.length) throw new Error('Authentication leaked into web storage');
  console.log('Swagger DOM authorization flows and repeated Try it out requests passed.');
} finally {
  dom.window.close();
}

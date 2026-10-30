import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { signal } from '@angular/core';
import { Registration } from './registration';
import { Session } from '../auth/session';
import { Api, ApiError } from '../shared/api';
import { editorPayload, emptyValues, resourceDefinitions } from './resources';
import { FANTASY_NAME_HELP_TEXT, PRICE_HELP_TEXT } from '../shared/field-label';
import { DESCRIPTION_MAX_LENGTH } from '../shared/description';

describe('Catalogue drafts and submission', () => {
  const session = { current: signal({ authenticated: true, can_create: true, csrf_token: 'disposable-test-csrf' }), canCreate: signal(true), ensure: vi.fn(), openLogin: vi.fn(), expire: vi.fn() };
  const api = { request: vi.fn() };
  beforeEach(async () => {
    vi.clearAllMocks(); session.ensure.mockResolvedValue(session.current());
    session.canCreate.set(true);
    await TestBed.configureTestingModule({imports:[Registration],providers:[provideRouter([]),{provide:Session,useValue:session},{provide:Api,useValue:api}]}).compileComponents();
  });
  it('omits absent tier and preserves Unicode; explicit tier is sent without client reordering', () => {
    const draft = { ...emptyValues(resourceDefinitions.work_classifications), work_classification_name:'favorite',display_name_work_classifications:'Favorito 🐍' };
    expect(editorPayload(resourceDefinitions.work_classifications,draft)).not.toHaveProperty('tier');
    expect(editorPayload(resourceDefinitions.work_classifications,{...draft,tier:'2'})).toEqual({work_classification_name:'favorite',display_name_work_classifications:'Favorito 🐍',description_work_classifications:null,tier:2});
  });
  it('shares the exact fantasy label and tooltip across all resources in create and edit modes',async()=>{
    const fixture=TestBed.createComponent(Registration),component=fixture.componentInstance;await fixture.whenStable();
    for(const resource of ['platforms','tags','work_classifications'] as const){
      component.choose(resource);
      for(const editing of [false,true]){component.original.set(editing?{[resourceDefinitions[resource].display]:'Existing name'}:null);fixture.detectChanges();const root=fixture.nativeElement as HTMLElement,key=resourceDefinitions[resource].display;
        expect(root.querySelector('label[for="'+key+'"]')?.textContent).toBe('* Nome Fantasia');expect(root.querySelector('#'+key+'-help')?.textContent).toBe(FANTASY_NAME_HELP_TEXT);expect(root.querySelector('p#'+key+'-help')).toBeNull();expect(root.querySelector('#'+key)?.getAttribute('aria-describedby')).toContain(key+'-help');
      }
    }
  });
  it('preserves exact decimal text and explicit false independently of paid status', () => {
    expect(editorPayload(resourceDefinitions.platforms,{...emptyValues(resourceDefinitions.platforms),platform_is_paid:'true',platform_is_episodes:'false',platform_is_duration_time:'false',price_amount:'123,4567890123456789',platform_access_types:'website'})).toMatchObject({price_amount:'123.4567890123456789',platform_is_paid:true,platform_access_types:['website'],platform_url:null});
  });
  it('renders the focused platform copy, navigation and controls and creates with untouched checkboxes',async()=>{
    const fixture=TestBed.createComponent(Registration),component=fixture.componentInstance;await fixture.whenStable();fixture.detectChanges();
    const root=fixture.nativeElement as HTMLElement;
    const back=root.querySelector('.page-links a') as HTMLAnchorElement;
    expect(root.querySelectorAll('.page-links a')).toHaveLength(1);expect(back.textContent).toContain('Voltar a Cadastrar');expect(back.getAttribute('href')).toBe('/cadastrar');expect(back.classList.contains('home-return')).toBe(true);expect(root.textContent).not.toContain('Voltar ao início');
    expect(root.querySelector('#platform_name-help')?.textContent).toBe(FANTASY_NAME_HELP_TEXT);expect((root.querySelector('#platform_name-help') as HTMLElement).hidden).toBe(true);expect(root.querySelector('p#platform_name-help')).toBeNull();
    expect([...root.querySelectorAll('label .required-star')].map(star=>star.parentElement?.getAttribute('for'))).toEqual(['platform_name','platform_access_types']);
    for(const key of ['platform_is_paid','platform_is_episodes','platform_is_duration_time']){
      const input=root.querySelector('#'+key) as HTMLInputElement;expect(input.checked).toBe(false);expect(input.indeterminate).toBe(false);expect(input.required).toBe(false);
      const label=input.closest('label')!;label.click();fixture.detectChanges();expect(input.checked).toBe(true);label.click();fixture.detectChanges();expect(input.checked).toBe(false);
    }
    expect(root.textContent).not.toMatch(/Por responder|Limpar resposta|Valor exato enviado|Opcional|opcional/);
    expect(root.querySelector('#price_amount')).toBeNull();expect(root.querySelector('#price_currency')).toBeNull();
    component.setValue('platform_is_paid','true');fixture.detectChanges();
    expect(root.querySelector('#price_amount-help')?.textContent).toBe(PRICE_HELP_TEXT);
    expect(root.querySelector('#price_currency-help')).toBeNull();
    expect(root.querySelector('#price_currency')).toBeNull();
    for(const key of ['platform_access_types']){const select=root.querySelector('#'+key) as HTMLSelectElement;expect(select.value).toBe('');expect(select.selectedOptions[0].textContent).toBe('Selecione uma opção');}
    component.setValue('platform_is_paid','false');fixture.detectChanges();
    component.setValue('platform_name','Disposable platform');component.setValue('platform_access_types','application');
    api.request.mockResolvedValueOnce({id_platforms:'PL0000001',platform_name:'Disposable platform'});await component.submit(new Event('submit'));
    expect(api.request).toHaveBeenLastCalledWith('/platforms','POST',{platform_name:'Disposable platform',platform_is_paid:false,platform_is_episodes:false,platform_is_duration_time:false,platform_access_types:['application']},'disposable-test-csrf');expect(component.success()?.id).toBe('PL0000001');
  });
  it('retains paid drafts across toggles, omits hidden invalid values and clears them after creation',async()=>{
    const fixture=TestBed.createComponent(Registration),component=fixture.componentInstance;await fixture.whenStable();fixture.detectChanges();const root=fixture.nativeElement as HTMLElement;
    for(const key of ['platform_name','platform_access_types']){const label=root.querySelector('label[for="'+key+'"]')!;expect(label.textContent?.trim().startsWith('*')).toBe(true);expect(label.firstElementChild?.classList.contains('required-star')).toBe(true);}
    component.setValue('platform_is_paid','true');component.setValue('price_amount','23,5');component.setValue('price_currency','EUR');fixture.detectChanges();expect(root.querySelector('#price_amount')).not.toBeNull();
    component.setValue('platform_is_paid','false');fixture.detectChanges();expect(root.querySelector('#price_amount')).toBeNull();expect(root.querySelector('#price_currency')).toBeNull();
    component.setValue('platform_is_paid','true');fixture.detectChanges();expect((root.querySelector('#price_amount') as HTMLInputElement).value).toBe('23,50');expect(root.querySelector('#price_currency')?.textContent).toContain('EUR — Euro');
    component.setValue('price_amount','-1');component.setValue('platform_name','Disposable retained draft');component.setValue('platform_access_types','application');await component.submit(new Event('submit'));expect(component.fieldError('price_amount')).not.toBe('');expect(api.request).not.toHaveBeenCalled();
    component.setValue('platform_is_paid','false');api.request.mockResolvedValueOnce({id_platforms:'PL0000001',platform_name:'Disposable retained draft'});await component.submit(new Event('submit'));
    const payload=api.request.mock.calls.at(-1)![2];expect(payload).not.toHaveProperty('price_amount');expect(payload).not.toHaveProperty('price_currency');expect(component.values()['price_amount']).toBe('');expect(component.values()['price_currency']).toBe('');expect(component.values()['platform_is_paid']).toBe('false');
  });
  it('orders access and URL before checkboxes with paid last, then requires currency only for valid price including zero',async()=>{
    const fixture=TestBed.createComponent(Registration),component=fixture.componentInstance;await fixture.whenStable();fixture.detectChanges();const root=fixture.nativeElement as HTMLElement;
    expect([...root.querySelectorAll('input[type=checkbox]')].map(input=>input.id)).toEqual(['platform_is_episodes','platform_is_duration_time','platform_is_paid']);
    expect([...root.querySelectorAll('label[for]')].slice(0,2).map(label=>label.textContent?.trim())).toEqual(['* Nome Fantasia','* Onde acessar']);
    component.setValue('platform_access_types','website');fixture.detectChanges();expect([...root.querySelectorAll('label[for]')].slice(0,3).map(label=>label.getAttribute('for'))).toEqual(['platform_name','platform_access_types','platform_url']);
    component.setValue('platform_access_types','application');component.setValue('platform_name','Disposable paid');component.setValue('platform_is_paid','true');fixture.detectChanges();expect(root.querySelector('#price_amount')).not.toBeNull();expect(root.querySelector('#price_currency')).toBeNull();
    component.setValue('price_amount','-1');await component.submit(new Event('submit'));fixture.detectChanges();expect(component.fieldError('price_amount')).not.toBe('');expect(root.querySelector('#price_currency')).toBeNull();expect(api.request).not.toHaveBeenCalled();
    component.setValue('price_amount','0');fixture.detectChanges();expect(root.querySelector('label[for=price_currency]')?.textContent?.trim()).toBe('* Moeda');await component.submit(new Event('submit'));expect(component.fieldError('price_currency')).toContain('Selecione');expect(api.request).not.toHaveBeenCalled();
    component.setValue('price_currency','EUR');component.setValue('price_amount','');fixture.detectChanges();expect(root.querySelector('#price_currency')).toBeNull();expect(component.values()['price_currency']).toBe('EUR');
    api.request.mockResolvedValueOnce({id_platforms:'PL0000001',platform_name:'Disposable paid'});await component.submit(new Event('submit'));expect(component.fieldError('price_currency')).toBe('');expect(api.request.mock.calls.at(-1)![2]).not.toHaveProperty('price_currency');expect(api.request.mock.calls.at(-1)![2]).not.toHaveProperty('price_amount');
  });
  it('prevents concurrent POST and clears the draft only after confirmed success', async () => {
    const fixture = TestBed.createComponent(Registration); const component=fixture.componentInstance;
    await Promise.resolve(); component.choose('tags');
    component.setValue('tag_name','draft'); component.setValue('display_name_tags','Rótulo 🐍'); component.setValue('description_tags','draft description');
    let resolve!: (value: unknown) => void;
    api.request.mockReturnValue(new Promise(done=>resolve=done));
    const first=component.submit(new Event('submit')); await component.submit(new Event('submit'));
    expect(api.request).toHaveBeenCalledTimes(1);
    expect(api.request).toHaveBeenCalledWith('/tags','POST',expect.objectContaining({tag_name:'draft'}),'disposable-test-csrf');
    resolve({id_tags:'TG0000001',display_name_tags:'Rótulo 🐍'}); await first;
    expect(component.success()?.id).toBe('TG0000001'); expect(component.values()['tag_name']).toBe('');
    component.another(); expect(component.values()['tag_name']).toBe('');
  });
  it.each([new ApiError(422,'VALIDATION_ERROR',[{loc:['body','tag_name']}]),new ApiError(0),new ApiError(401,'INVALID_TOKEN'),new ApiError(403,'CSRF_REJECTED')])('retains draft after failure without automatic POST retry', async error => {
    const component=TestBed.createComponent(Registration).componentInstance; await Promise.resolve(); component.choose('tags');
    component.setValue('tag_name','saved_draft'); component.setValue('display_name_tags','Não perder 🐍'); component.setValue('description_tags','Texto');
    api.request.mockRejectedValue(error); await component.submit(new Event('submit'));
    expect(component.values()['display_name_tags']).toBe('Não perder 🐍'); expect(component.success()).toBeNull(); expect(api.request).toHaveBeenCalledTimes(1);
    if (error.status===401) expect(session.expire).toHaveBeenCalled();
  });
  it('does not call mutation API when current permissions deny creation', async () => {
    const component=TestBed.createComponent(Registration).componentInstance; await Promise.resolve(); session.canCreate.set(false);
    await component.submit(new Event('submit')); expect(api.request).not.toHaveBeenCalled(); expect(component.notice()).toContain('supervisor');
  });
  it('blocks oversized submitted descriptions but preserves omitted historical descriptions during edits',async()=>{
    const fixture=TestBed.createComponent(Registration),component=fixture.componentInstance;await fixture.whenStable();component.choose('tags');component.setValue('tag_name','description_case');component.setValue('display_name_tags','Description case');const historical='👩🏽‍💻'.repeat(DESCRIPTION_MAX_LENGTH+1);component.setValue('description_tags',historical);await component.submit(new Event('submit'));expect(component.fieldError('description_tags')).not.toBe('');expect(api.request).not.toHaveBeenCalled();
    component.original.set({id_tags:'TG0000001',tag_name:'description_case',display_name_tags:'Description case',description_tags:historical});component.setValue('display_name_tags','Renamed');api.request.mockResolvedValueOnce({id_tags:'TG0000001',display_name_tags:'Renamed'});await component.submit(new Event('submit'));expect(api.request).toHaveBeenLastCalledWith('/tags/TG0000001','PUT',{display_name_tags:'Renamed'},'disposable-test-csrf');
  });
  it('reveals technical input only on name completion and keeps manual names across suggestions',async()=>{
    const component=TestBed.createComponent(Registration).componentInstance;await Promise.resolve();component.choose('tags');
    component.setValue('display_name_tags','Ficção épica');expect(component.technicalVisible()).toBe(false);expect(component.suggestion()).toBe('ficcao_epica');
    component.completeName(false);expect(component.technicalVisible()).toBe(true);component.setValue('tag_name','custom_name');component.setValue('display_name_tags','Another name');
    expect(component.values()['tag_name']).toBe('custom_name');
  });
  it('retrieves a selected existing record without mutation, and PUT sends only changed editable fields',async()=>{
    const component=TestBed.createComponent(Registration).componentInstance;await Promise.resolve();component.choose('tags');component.setValue('display_name_tags','Create draft');
    component.pendingExisting.set({id_tags:'TG0000001',display_name_tags:'Existing'});component.pendingExisting.set(null);
    expect(component.values()['display_name_tags']).toBe('Create draft');expect(api.request).not.toHaveBeenCalled();
    component.pendingExisting.set({id_tags:'TG0000001',display_name_tags:'Existing'});api.request.mockResolvedValueOnce({id_tags:'TG0000001',tag_name:'original',display_name_tags:'Existing',description_tags:'Old'});
    await component.confirmExisting();expect(api.request).toHaveBeenLastCalledWith('/tags/TG0000001');expect(component.editing()).toBe(true);expect(component.technicalVisible()).toBe(true);
    component.setValue('description_tags','');api.request.mockResolvedValueOnce({id_tags:'TG0000001',tag_name:'original',display_name_tags:'Existing',description_tags:null});
    await component.submit(new Event('submit'));expect(api.request).toHaveBeenLastCalledWith('/tags/TG0000001','PUT',{description_tags:null},'disposable-test-csrf');
    component.choose('platforms');expect(component.editing()).toBe(false);expect(component.values()).not.toHaveProperty('tag_name');
  });
  it('requires access, accepts untouched false booleans, preserves a hidden URL and resets only on success',async()=>{
    const fixture=TestBed.createComponent(Registration),component=fixture.componentInstance;await fixture.whenStable();
    component.setValue('platform_name','Library');await component.submit(new Event('submit'));
    expect(api.request).not.toHaveBeenCalled();expect(component.fieldError('platform_is_paid')).toBe('');expect(component.fieldError('platform_access_types')).toContain('Selecione');
    for(const key of ['platform_is_paid','platform_is_episodes','platform_is_duration_time'])component.setValue(key,'false');
    component.setValue('platform_access_types','website');component.setValue('platform_url','https://example.org/draft');fixture.detectChanges();expect(fixture.nativeElement.querySelector('#platform_url')).not.toBeNull();
    component.setValue('platform_access_types','application');fixture.detectChanges();expect(fixture.nativeElement.querySelector('#platform_url')).toBeNull();expect(component.values()['platform_url']).toBe('https://example.org/draft');
    component.setValue('platform_access_types','website');fixture.detectChanges();expect(fixture.nativeElement.querySelector('#platform_url').value).toBe('https://example.org/draft');
    component.setValue('platform_access_types','application');component.setValue('platform_is_paid','true');component.setValue('price_amount','0');component.setValue('price_currency','EUR');
    api.request.mockRejectedValueOnce(new ApiError(422));await component.submit(new Event('submit'));expect(component.values()['platform_url']).toBe('https://example.org/draft');
    api.request.mockResolvedValueOnce({id_platforms:'PL0000001',platform_name:'Library'});await component.submit(new Event('submit'));
    const payload=api.request.mock.calls.at(-1)![2];expect(payload).toMatchObject({platform_is_paid:true,price_amount:'0',price_currency:'EUR',platform_access_types:['application']});expect(payload).not.toHaveProperty('platform_url');
    expect(component.success()?.id).toBe('PL0000001');expect(component.values()).toEqual(emptyValues(resourceDefinitions.platforms));component.choose('tags');component.choose('platforms');expect(component.values()['platform_url']).toBe('');
  });
});

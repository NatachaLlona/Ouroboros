import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { signal } from '@angular/core';
import { Registration } from './registration';
import { registrationDefinitions,resourceDefinitions,editorPayload } from './resources';
import { Session } from '../auth/session';
import { Api,ApiError } from '../shared/api';
import { UnsavedChanges } from '../shared/unsaved-changes';
import { DESCRIPTION_MAX_LENGTH } from '../shared/description';
import { FANTASY_NAME_HELP_TEXT } from '../shared/field-label';

describe('Tag submenu and existing category create contract',()=>{
  const session={current:signal({authenticated:true,can_create:true,csrf_token:'test-only'}),canCreate:signal(true),ensure:vi.fn(),openLogin:vi.fn(),expire:vi.fn()};
  const api={request:vi.fn()};
  beforeEach(()=>{vi.clearAllMocks();session.ensure.mockResolvedValue(session.current());api.request.mockReset();TestBed.configureTestingModule({imports:[Registration],providers:[provideRouter([]),{provide:Session,useValue:session},{provide:Api,useValue:api}]});});
  async function setup(){const fixture=TestBed.createComponent(Registration);await fixture.whenStable();return {fixture,component:fixture.componentInstance,root:fixture.nativeElement as HTMLElement};}
  it('keeps the exact three main choices, defaults to Tag immediately and hides submenu elsewhere',async()=>{
    const {fixture,component,root}=await setup();expect([...root.querySelectorAll('.type-option')].map(button=>button.textContent)).toEqual(['Plataforma','Tag','Classificação da Obra']);expect(root.querySelector('.registration-submenu')).toBeNull();
    (root.querySelectorAll('.type-option')[1] as HTMLButtonElement).click();await fixture.whenStable();expect(component.selected()).toBe('tags');expect(root.querySelector('#display_name_tags')).not.toBeNull();
    const options=root.querySelectorAll('.registration-submenu button') as NodeListOf<HTMLButtonElement>;expect([...options].map(button=>button.textContent)).toEqual(['Tag','Categoria de Tag']);expect(options[0].getAttribute('aria-pressed')).toBe('true');expect(options[1].type).toBe('button');
    options[1].click();await fixture.whenStable();expect(root.querySelector('#display_name_tag_categories')).not.toBeNull();expect(options[1].getAttribute('aria-pressed')).toBe('true');expect(root.querySelectorAll('.type-option')[1].getAttribute('aria-pressed')).toBe('true');
    (root.querySelectorAll('.type-option')[1] as HTMLButtonElement).click();await fixture.whenStable();expect(component.selected()).toBe('tags');
    await component.choose('platforms');await fixture.whenStable();expect(root.querySelector('.registration-submenu')).toBeNull();
    await component.choose('work_classifications');await fixture.whenStable();expect(root.querySelector('.registration-submenu')).toBeNull();expect(Object.keys(resourceDefinitions)).toEqual(['platforms','tags','work_classifications']);
  });
  it('uses the same discard guard in both submenu directions and on leaving the main Tag section',async()=>{
    const {component}=await setup(),unsaved=TestBed.inject(UnsavedChanges);await component.choose('tags');component.setValue('display_name_tags','Keep tag');
    const cancelled=component.choose('tag_categories');expect(unsaved.asking()).toBe(true);unsaved.decide(false);await cancelled;expect(component.selected()).toBe('tags');expect(component.values()['display_name_tags']).toBe('Keep tag');
    const accepted=component.choose('tag_categories');unsaved.decide(true);await accepted;component.setValue('display_name_tag_categories','Keep category');
    for(const target of ['tags','platforms'] as const){const change=component.choose(target);expect(unsaved.asking()).toBe(true);unsaved.decide(false);await change;expect(component.selected()).toBe('tag_categories');expect(component.values()['display_name_tag_categories']).toBe('Keep category');}
    const leave=component.choose('tags');unsaved.decide(true);await leave;expect(component.values()['display_name_tags']).toBe('');expect(api.request).not.toHaveBeenCalled();
  });
  it('reuses labels, description configuration, technical revelation and only real editable fields',async()=>{
    const {fixture,component,root}=await setup();await component.choose('tag_categories');await fixture.whenStable();
    expect(root.textContent).toContain('Cadastrar Categoria de Tag');expect(root.querySelector('label[for=display_name_tag_categories]')?.textContent).toBe('* Nome Fantasia');expect(root.querySelector('#display_name_tag_categories-help')?.textContent).toBe(FANTASY_NAME_HELP_TEXT);
    expect(root.querySelector('app-description-input')).not.toBeNull();expect(root.querySelector('.description-counter')?.textContent).toContain(String(DESCRIPTION_MAX_LENGTH));expect(root.querySelector('#description_tag_categories-help')).toBeNull();
    component.setValue('display_name_tag_categories','Gênero épico');fixture.detectChanges();expect(root.querySelector('#tag_category_name')).toBeNull();component.completeName(false);fixture.detectChanges();
    expect((root.querySelector('#tag_category_name') as HTMLInputElement).placeholder).toBe('genero_epico');
    expect([...root.querySelectorAll('form input, form textarea')].map(input=>input.id)).toEqual(['display_name_tag_categories','tag_category_name','description_tag_categories']);
    const payload=editorPayload(registrationDefinitions.tag_categories,component.values());expect(payload).toEqual({tag_category_name:'genero_epico',display_name_tag_categories:'Gênero épico',description_tag_categories:null});
  });
  it('validates required names, technical syntax and the centralized description limit before POST',async()=>{
    const {component}=await setup();await component.choose('tag_categories');await component.submit(new Event('submit'));expect(component.fieldError('display_name_tag_categories')).not.toBe('');
    component.setValue('display_name_tag_categories','Category');component.setValue('tag_category_name','Invalid Name');await component.submit(new Event('submit'));expect(component.fieldError('tag_category_name')).not.toBe('');
    component.setValue('tag_category_name','valid_name');component.setValue('description_tag_categories','x'.repeat(DESCRIPTION_MAX_LENGTH+1));await component.submit(new Event('submit'));expect(component.fieldError('description_tag_categories')).not.toBe('');expect(api.request).not.toHaveBeenCalled();
  });
  it('POSTs only category fields once, resets immediately after success and reuses Cadastrar outro',async()=>{
    const {fixture,component,root}=await setup();await component.choose('tag_categories');component.setValue('display_name_tag_categories','Category');component.setValue('tag_category_name','custom_category');component.setValue('description_tag_categories','Unicode 👩🏽‍💻');
    let resolve!:(value:unknown)=>void;api.request.mockReturnValueOnce(new Promise(done=>resolve=done));const pending=component.submit(new Event('submit'));await component.submit(new Event('submit'));fixture.detectChanges();expect(root.querySelector('.registration-submenu button')?.hasAttribute('disabled')).toBe(true);
    expect(api.request).toHaveBeenCalledTimes(1);expect(api.request).toHaveBeenCalledWith('/tag_categories','POST',{tag_category_name:'custom_category',display_name_tag_categories:'Category',description_tag_categories:'Unicode 👩🏽‍💻'},'test-only');
    resolve({id_tag_categories:'TC0000001',display_name_tag_categories:'Category'});await pending;await fixture.whenStable();expect(component.values()).toEqual({tag_category_name:'',display_name_tag_categories:'',description_tag_categories:''});expect(root.querySelector('.success')?.textContent).toContain('TC0000001');
    (root.querySelector('.success>button.button') as HTMLButtonElement).click();await fixture.whenStable();expect(component.success()).toBeNull();expect(component.values()['display_name_tag_categories']).toBe('');expect(root.querySelector('#display_name_tag_categories')).not.toBeNull();
  });
  it.each([new ApiError(422,'VALIDATION_ERROR'),new ApiError(409),new ApiError(0),new ApiError(401,'INVALID_TOKEN')])('preserves the category draft and existing feedback after API error',async error=>{
    const {fixture,component,root}=await setup();await component.choose('tag_categories');component.setValue('display_name_tag_categories','Keep category');component.setValue('description_tag_categories','Keep description');const values={...component.values()};api.request.mockRejectedValueOnce(error);await component.submit(new Event('submit'));await fixture.whenStable();
    expect(component.values()).toEqual(values);expect(component.success()).toBeNull();expect(root.querySelector('.form-error')).not.toBeNull();expect(api.request).toHaveBeenCalledTimes(1);expect(component.busy()).toBe(false);
  });
});

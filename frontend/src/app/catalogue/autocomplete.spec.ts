import { TestBed } from '@angular/core/testing';
import { NameAutocomplete } from './autocomplete';
import { Api } from '../shared/api';
import { editorPayload, effectiveTechnical, resourceDefinitions, technicalSuggestion } from './resources';

describe('Fantasy-name keyboard completion and safe suggestions',()=>{
  const api={request:vi.fn()};
  beforeEach(()=>{vi.useFakeTimers();api.request.mockReset();TestBed.configureTestingModule({imports:[NameAutocomplete],providers:[{provide:Api,useValue:api}]});});
  afterEach(()=>vi.useRealTimers());
  function create(){const fixture=TestBed.createComponent(NameAutocomplete);fixture.componentRef.setInput('definition',resourceDefinitions.tags);fixture.detectChanges();return fixture;}
  it('debounces escaped substring requests and ignores stale results',async()=>{
    const fixture=create(),component=fixture.componentInstance;let resolve!:(value:unknown)=>void;
    api.request.mockReturnValueOnce(new Promise(done=>resolve=done)).mockResolvedValueOnce({count:1,page:1,items:[{id_tags:'TG0000002',display_name_tags:'new'}]});
    component.typed({target:{value:'50%_'}} as unknown as Event);await vi.advanceTimersByTimeAsync(249);expect(api.request).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);expect(api.request).toHaveBeenLastCalledWith('/tags','GET',undefined,undefined,expect.objectContaining({display_name_tags:'%50\\%\\_%',page_size:20}));
    component.typed({target:{value:'new'}} as unknown as Event);await vi.advanceTimersByTimeAsync(250);
    resolve({count:1,page:1,items:[{id_tags:'TG0000001',display_name_tags:'old'}]});await Promise.resolve();expect(component.items()[0]['display_name_tags']).toBe('new');
  });
  it('gives active options and unique prefix completion precedence over revealing technical input',()=>{
    const component=create().componentInstance;component.value.set('Fan');component.items.set([{id_tags:'TG0000001',display_name_tags:'Fantasia'}]);component.count.set(1);component.open.set(true);
    const selected=vi.fn(),completed=vi.fn();component.selected.subscribe(selected);component.completed.subscribe(completed);
    const event=new KeyboardEvent('keydown',{key:'Enter',cancelable:true});component.key(event);expect(event.defaultPrevented).toBe(true);expect(selected).toHaveBeenCalledTimes(1);expect(completed).not.toHaveBeenCalled();
    component.value.set('tas');expect(component.suffix()).toBe('');component.key(new KeyboardEvent('keydown',{key:'Enter',cancelable:true}));expect(completed).toHaveBeenCalledWith(true);
    component.key(new KeyboardEvent('keydown',{key:'Tab',cancelable:true}));expect(completed).toHaveBeenCalledTimes(2);
  });
  it('uses the effective suggestion without overwriting custom or original names',()=>{
    expect(technicalSuggestion('Ficção épica 🐉')).toBe('ficcao_epica');expect(technicalSuggestion('🐉')).toBe('');
    expect(effectiveTechnical(resourceDefinitions.tags,{display_name_tags:'Ficção épica',tag_name:''},false)).toBe('ficcao_epica');
    expect(effectiveTechnical(resourceDefinitions.tags,{display_name_tags:'Changed',tag_name:'original'},true)).toBe('original');
    expect(editorPayload(resourceDefinitions.tags,{display_name_tags:'Changed',tag_name:'original',description_tags:''},{display_name_tags:'Old',tag_name:'original',description_tags:'Old description'})).toEqual({display_name_tags:'Changed',description_tags:null});
  });
  it('anchors at the input, caps twenty options, offers no paging, and hides empty matches',async()=>{
    const fixture=create(),component=fixture.componentInstance;
    api.request.mockResolvedValueOnce({count:30,page:1,page_size:20,items:Array.from({length:22},(_,index)=>({id_tags:'TG'+String(index+1).padStart(7,'0'),display_name_tags:'Fantasy '+index,tag_name:'hidden_technical'}))});
    component.value.set('Fantasy');component.open.set(true);await component.search();fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.completion-wrap .autocomplete-panel')).not.toBeNull();expect(fixture.nativeElement.querySelectorAll('[role=option]')).toHaveLength(20);expect(fixture.nativeElement.textContent).toContain('Continue digitando para refinar a busca');expect(fixture.nativeElement.textContent).not.toContain('hidden_technical');expect(fixture.nativeElement.textContent).not.toMatch(/Anterior|Seguinte|Sem resultados/);
    fixture.nativeElement.querySelectorAll('li').forEach((item:HTMLElement)=>item.scrollIntoView=vi.fn());
    const selected=vi.fn();component.selected.subscribe(selected);component.key(new KeyboardEvent('keydown',{key:'ArrowDown',cancelable:true}));component.key(new KeyboardEvent('keydown',{key:'Enter',cancelable:true}));expect(selected).toHaveBeenCalledWith(expect.objectContaining({display_name_tags:'Fantasy 0'}));
    api.request.mockResolvedValueOnce({count:0,page:1,page_size:10,items:[]});await component.search();fixture.detectChanges();expect(fixture.nativeElement.querySelector('.autocomplete-panel')).toBeNull();
  });
  it('distinguishes a recoverable lookup failure from no matches',async()=>{
    const fixture=create(),component=fixture.componentInstance;component.value.set('Fantasy');component.open.set(true);api.request.mockRejectedValueOnce(new Error('Lookup failed'));await component.search();fixture.detectChanges();
    expect(component.searchError()).not.toBe('');expect(fixture.nativeElement.querySelector('[role=alert]')).not.toBeNull();expect(fixture.nativeElement.querySelector('.autocomplete-panel')).toBeNull();
    component.key(new KeyboardEvent('keydown',{key:'Escape'}));expect(component.open()).toBe(false);
  });
});

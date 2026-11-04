import { assistantGreeting, frontendConfig, loadFrontendConfig } from './frontend.config';

describe('Public runtime presentation configuration',()=>{
  const original=structuredClone(frontendConfig);
  afterEach(()=>{Object.assign(frontendConfig,structuredClone(original));vi.unstubAllGlobals();});
  function respond(value:unknown){vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:true,json:async()=>value}));}
  it('loads names, colors and images before component construction',async()=>{
    const config=structuredClone(original);config.nome_assistente_2='Runtime assistant';config.assistant_2_colors.primary='#EFEFEF';
    respond(config);await loadFrontendConfig();
    expect(frontendConfig.nome_assistente_2).toBe('Runtime assistant');
    expect(assistantGreeting(true)).toContain('Runtime assistant');
    expect(frontendConfig.assistant_2_colors.primary).toBe('#EFEFEF');
  });
  it('rejects private/unknown keys without changing the current presentation',async()=>{
    respond({...original,OPENAI_API_KEY:'disposable-test-placeholder'});
    await expect(loadFrontendConfig()).rejects.toThrow();expect(frontendConfig).toEqual(original);
  });
  it('rejects CSS injection and external or traversing image paths',async()=>{
    for(const path of ['https://example.invalid/image.png','/frontend/../private']){
      respond({...original,assistant_image:path});await expect(loadFrontendConfig()).rejects.toThrow();
    }
    respond({...original,assistant_colors:{...original.assistant_colors,accent:'red;background:black'}});
    await expect(loadFrontendConfig()).rejects.toThrow();expect(frontendConfig).toEqual(original);
  });
});

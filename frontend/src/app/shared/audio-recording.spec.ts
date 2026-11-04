import { TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';
import { Api } from './api';
import { Session } from '../auth/session';
import { AssistantContext, SiteAssistant } from './site-assistant';
import { AudioLevelMeter } from './audio-level-meter';

describe('Microphone recording lifecycle',()=>{
  const api={request:vi.fn()},session={current:signal({authenticated:true,csrf_token:'unit-csrf'}),expire:vi.fn(),ensure:vi.fn()};
  const options={max_audio_bytes:67108864,max_duration_seconds:600,request_timeout_seconds:1500,recording_chunk_ms:250,audio_bits_per_second:64000};
  let originalMedia:PropertyDescriptor|undefined;
  let stopTrack:ReturnType<typeof vi.fn>;
  class Recorder {
    static isTypeSupported=()=>true;static last:Recorder;
    state='inactive';onstop:(()=>void)|null=null;ondataavailable:((event:{data:Blob})=>void)|null=null;onerror:(()=>void)|null=null;
    constructor(readonly stream:MediaStream,readonly options:MediaRecorderOptions){Recorder.last=this;}
    start=vi.fn(()=>this.state='recording');
    stop=vi.fn(()=>{this.state='inactive';this.ondataavailable?.({data:new Blob(['synthetic audio'])});this.onstop?.();});
  }
  beforeEach(()=>{
    vi.clearAllMocks();originalMedia=Object.getOwnPropertyDescriptor(navigator,'mediaDevices');stopTrack=vi.fn();
    Object.defineProperty(navigator,'mediaDevices',{configurable:true,value:{getUserMedia:vi.fn().mockResolvedValue({getTracks:()=>[{stop:stopTrack}]})}});
    vi.stubGlobal('MediaRecorder',Recorder);
    api.request.mockImplementation((path:string)=>path.endsWith('/options')?Promise.resolve(options):Promise.resolve({text:'Transcribed speech.',language:'en',complete:true}));
    TestBed.configureTestingModule({imports:[SiteAssistant],providers:[{provide:Api,useValue:api},{provide:Session,useValue:session}]});
  });
  afterEach(()=>{vi.useRealTimers();vi.unstubAllGlobals();if(originalMedia)Object.defineProperty(navigator,'mediaDevices',originalMedia);else Reflect.deleteProperty(navigator,'mediaDevices');});
  async function create(){
    const fixture=TestBed.createComponent(SiteAssistant);await fixture.whenStable();
    TestBed.runInInjectionContext(()=>TestBed.inject(AssistantContext).registerForm(document.createElement('form'),{destroyed:false,onDestroy:()=>()=>{}}));
    await fixture.whenStable();fixture.componentInstance.open.set(true);fixture.detectChanges();return fixture;
  }
  it('discards capture without posting or changing editable text',async()=>{
    const component=(await create()).componentInstance;component.message.set('Existing text');await component.record();
    expect(component.state()).toBe('recording');component.message.set('Existing text with manual edits');component.discardRecording();
    expect(component.state()).toBe('idle');expect(component.message()).toBe('Existing text with manual edits');expect(stopTrack).toHaveBeenCalled();
    expect(component.recordingStream()).toBeNull();expect(api.request.mock.calls.some(call=>call[0]==='/browser/transcription')).toBe(false);
  });
  it('keeps recording through pauses and uses the configured ten-minute timer',async()=>{
    const component=(await create()).componentInstance;vi.useFakeTimers();await component.record();
    await vi.advanceTimersByTimeAsync(599999);expect(component.state()).toBe('recording');expect(Recorder.last.stop).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);expect(Recorder.last.stop).toHaveBeenCalledOnce();
    expect(api.request.mock.calls.filter(call=>call[0]==='/browser/transcription')).toHaveLength(1);
    expect(Recorder.last.options.audioBitsPerSecond).toBe(options.audio_bits_per_second);
  });
  it('finishes explicitly, preserves edits made during processing and never auto-sends',async()=>{
    const component=(await create()).componentInstance;let finish!:(value:unknown)=>void;
    api.request.mockImplementation((path:string)=>path.endsWith('/options')?Promise.resolve(options):new Promise(resolve=>finish=resolve));
    component.message.set('Before');await component.record();await component.record();expect(component.state()).toBe('transcribing');
    component.message.set('Before and edited while processing');finish({text:'Full transcription.',language:'en',complete:true});await Promise.resolve();await Promise.resolve();
    expect(component.message()).toBe('Before and edited while processing\nFull transcription.');
    expect(api.request.mock.calls.find(call=>call[0]==='/browser/transcription')?.[7]).toBe(options.request_timeout_seconds*1000);
    expect(api.request.mock.calls.some(call=>call[0].includes('/assistant/'))).toBe(false);
  });
  it('rejects an incomplete result and retains the original text',async()=>{
    const component=(await create()).componentInstance;api.request.mockImplementation((path:string)=>Promise.resolve(path.endsWith('/options')?options:{text:'Partial',language:'en',complete:false}));
    component.message.set('Keep');await component.record();await component.record();await Promise.resolve();await Promise.resolve();
    expect(component.message()).toBe('Keep');expect(component.error()).not.toBe('');
  });
});

describe('Real Web Audio level display',()=>{
  it('reacts to sampled amplitude and releases analysis without stopping owned recording tracks',async()=>{
    let amplitude=128;const frames:FrameRequestCallback[]=[];
    const source={connect:vi.fn(),disconnect:vi.fn()},analyser={fftSize:256,getByteTimeDomainData:(data:Uint8Array)=>data.fill(amplitude),disconnect:vi.fn()};
    const close=vi.fn().mockResolvedValue(undefined),stop=vi.fn();
    class Context {createMediaStreamSource=()=>source;createAnalyser=()=>analyser;resume=()=>Promise.resolve();close=close;}
    vi.stubGlobal('AudioContext',Context);vi.stubGlobal('requestAnimationFrame',(callback:FrameRequestCallback)=>{frames.push(callback);return frames.length;});vi.stubGlobal('cancelAnimationFrame',vi.fn());
    try{
      const fixture=TestBed.createComponent(AudioLevelMeter);fixture.componentRef.setInput('stream',{getTracks:()=>[{stop}]});await fixture.whenStable();
      frames.shift()!(40);expect(fixture.componentInstance.levels().at(-1)).toBe(0);
      amplitude=192;frames.shift()!(80);expect(fixture.componentInstance.levels().at(-1)).toBeGreaterThan(0);
      fixture.destroy();expect(source.disconnect).toHaveBeenCalled();expect(analyser.disconnect).toHaveBeenCalled();expect(close).toHaveBeenCalled();expect(stop).not.toHaveBeenCalled();
    }finally{vi.unstubAllGlobals();}
  });
});

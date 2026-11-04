import { Component, DestroyRef, effect, inject, input, signal } from '@angular/core';

/** Sample microphone pressure; the display never invents an animated waveform. */
@Component({selector:'app-audio-level-meter',template:`
  @if(unavailable()){<span class="assistant-help">Visualização de áudio indisponível.</span>}
  @else{<svg class="assistant-audio-levels" viewBox="0 0 160 28" role="img" aria-label="Intensidade do áudio captado pelo microfone" preserveAspectRatio="none">
    @for(level of levels();track $index){<rect [attr.x]="$index*5+1" [attr.y]="(28-(2+level*26))/2" width="3" [attr.height]="2+level*26" rx="1" />}
  </svg>}
`})
export class AudioLevelMeter {
  readonly stream=input.required<MediaStream>();readonly levels=signal<number[]>(Array(32).fill(0));readonly unavailable=signal(false);
  private context:AudioContext|null=null;private source:MediaStreamAudioSourceNode|null=null;private analyser:AnalyserNode|null=null;private frame:number|null=null;
  constructor(){effect(()=>{this.stop();this.start(this.stream());});inject(DestroyRef).onDestroy(()=>this.stop());}
  private start(stream:MediaStream):void{
    this.unavailable.set(false);this.levels.set(Array(32).fill(0));
    try{
      const AudioContextClass=window.AudioContext||(window as unknown as {webkitAudioContext?:typeof AudioContext}).webkitAudioContext;
      if(!AudioContextClass)throw new Error('Audio analysis unavailable');
      const context=new AudioContextClass();this.context=context;
      this.source=context.createMediaStreamSource(stream);const analyser=context.createAnalyser();this.analyser=analyser;
      analyser.fftSize=256;this.source.connect(analyser);
      const data=new Uint8Array(analyser.fftSize);let last=0,smoothed=0;
      const sample=(time:number)=>{
        if(this.context!==context)return;
        if(time-last>=40){
          analyser.getByteTimeDomainData(data);let squareSum=0;
          for(const value of data){const sample=(value-128)/128;squareSum+=sample*sample;}
          smoothed=smoothed*.65+Math.min(1,Math.sqrt(squareSum/data.length)*5)*.35;
          this.levels.update(levels=>[...levels.slice(1),smoothed]);last=time;
        }
        this.frame=requestAnimationFrame(sample);
      };
      void context.resume().catch(()=>{if(this.context===context){this.stop();this.unavailable.set(true);}});
      this.frame=requestAnimationFrame(sample);
    }catch{this.stop();this.unavailable.set(true);}
  }
  private stop():void{
    if(this.frame!==null)cancelAnimationFrame(this.frame);this.frame=null;
    this.source?.disconnect();this.source=null;this.analyser?.disconnect();this.analyser=null;
    const context=this.context;this.context=null;if(context)void context.close().catch(()=>{});
  }
}

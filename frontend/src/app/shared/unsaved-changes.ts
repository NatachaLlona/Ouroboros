import { Injectable, signal } from '@angular/core';
import { CanDeactivateFn } from '@angular/router';

/** One cancel-first discard prompt shared by router, resource changes and logout. */
@Injectable({providedIn:'root'})
export class UnsavedChanges {
  readonly asking=signal(false);
  private pending?:Promise<boolean>;private resolve?:(discard:boolean)=>void;
  private active?:()=>boolean|Promise<boolean>;
  register(check:()=>boolean|Promise<boolean>):()=>void{this.active=check;return()=>{if(this.active===check)this.active=undefined;};}
  allowExit():boolean|Promise<boolean>{return this.active?.()??true;}
  ask():Promise<boolean>{
    if(this.pending)return this.pending;
    this.pending=new Promise(resolve=>this.resolve=resolve);this.asking.set(true);return this.pending;
  }
  decide(discard:boolean):void{const resolve=this.resolve;this.resolve=undefined;this.pending=undefined;this.asking.set(false);resolve?.(discard);}
}
export const leaveRegistration:CanDeactivateFn<{canDeactivate:()=>boolean|Promise<boolean>}>=component=>component.canDeactivate();

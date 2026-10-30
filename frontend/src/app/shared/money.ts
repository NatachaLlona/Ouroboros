import { formatCurrency, registerLocaleData } from '@angular/common';
import portuguese from '@angular/common/locales/pt';

registerLocaleData(portuguese, 'pt-PT');

export const currencies = [
  { code: 'EUR', name: 'Euro' },
  { code: 'USD', name: 'Dólar americano' },
  { code: 'BRL', name: 'Real brasileiro' }
] as const;

/** Parse only ungrouped, nonnegative comma decimals; never guess separators. */
export function priceValue(text: string): string | null {
  if (!text.trim()) return null;
  if (!/^\d+(?:,\d+)?$/.test(text)) throw new Error('Invalid decimal input');
  const [whole, fraction] = text.split(',');
  return whole.replace(/^0+(?=\d)/, '') + (fraction === undefined ? '' : '.' + fraction);
}

/** Round the display with decimal arithmetic, preserving the exact API value. */
export function priceDisplay(text: string): string {
  const canonical = priceValue(text);
  if (canonical === null) return '';
  const [whole, fraction = ''] = canonical.split('.');
  let cents = BigInt(whole) * 100n + BigInt((fraction + '00').slice(0, 2));
  if (fraction.length > 2 && fraction[2] >= '5') cents++;
  const exact = (cents / 100n).toString() + ',' + (cents % 100n).toString().padStart(2, '0');
  // CurrencyPipe/formatCurrency format numbers, not arbitrary-precision Decimal.
  // Use Angular for representable displays and exact decimal text for large ones.
  if (cents > BigInt(Number.MAX_SAFE_INTEGER)) return exact;
  const formatted=formatCurrency(Number(cents) / 100, 'pt-PT', '', '', '1.2-2').replace(/[.\s\u00a0\u202f]/g, '');
  return formatted===exact?formatted:exact;
}

/** Expand a server Decimal exponent exactly, without parsing it as a float. */
export function priceRecordText(text:string):string {
  const match=/^(\d+)(?:\.(\d+))?[eE]([+-]?\d+)$/.exec(text);
  if(!match)return text.replace('.',',');
  const digits=match[1]+(match[2]||''),point=match[1].length+Number(match[3]);
  if(!Number.isSafeInteger(point)||Math.abs(point)>131072)return text;
  return point<=0?'0,'+'0'.repeat(-point)+digits:point>=digits.length?digits+'0'.repeat(point-digits.length):digits.slice(0,point)+','+digits.slice(point);
}

export function priceError(text: string): string {
  try { priceValue(text); return ''; }
  catch { return 'Use um valor não negativo, sem símbolos nem separadores de milhar; use vírgula para os centavos.'; }
}

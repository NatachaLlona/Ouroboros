export interface SelectOption {value:string;label:string;}

export function filterSelectOptions(options:readonly SelectOption[],query:string):readonly SelectOption[]{
  const text=query.trim().toLocaleLowerCase('pt');
  return options.filter(option=>option.label.toLocaleLowerCase('pt').includes(text));
}

export function uniqueSelectValues(values:readonly string[]):string[]{return [...new Set(values)];}

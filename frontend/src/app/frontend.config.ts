/** Public presentation only; no backend settings or credentials belong here. */
export const frontendConfig={
  nome_assistente:'Aurie',
  nome_assistente_2:'Evie',
  mensagem_boas_vindas_assistente:'Oi, meu nome é {nome_assistente}!',
  mensagem_boas_vindas_assistente_2:'Oi, meu nome é {nome_assistente_2}!',
  assistant_colors:{text:'#424A40',highlighted_text:'#4E3944',primary:'#FFFCF6',accent:'#4E3944',user_text:'#823746'},
  assistant_2_colors:{text:'#424A40',highlighted_text:'#4E3944',primary:'#FFFCF6',accent:'#4E3944',user_text:'#823746'}
} as const;

export function assistantGreeting(formAssistant:boolean):string{
  const template=formAssistant?frontendConfig.mensagem_boas_vindas_assistente_2:frontendConfig.mensagem_boas_vindas_assistente;
  return template.replaceAll('{nome_assistente}',frontendConfig.nome_assistente).replaceAll('{nome_assistente_2}',frontendConfig.nome_assistente_2);
}

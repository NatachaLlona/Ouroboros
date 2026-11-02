/** The same association viewed from either creation form; no nested create payloads. */
export const tagCategoryAssociations={
  tags:{owner:'tags',related:'tag_categories',ownerKey:'id_tags',relatedKey:'id_tag_categories',
    prefix:'tag-category',label:'Categorias de Tag',placeholder:'Selecione categorias',selectedCountLabel:'categorias selecionadas',
    emptyMessage:'Nenhuma categoria cadastrada.',noResultsMessage:'Nenhuma categoria encontrada.',loadingMessage:'A carregar categorias…',unnamedLabel:'Categoria sem nome'},
  tag_categories:{owner:'tag_categories',related:'tags',ownerKey:'id_tag_categories',relatedKey:'id_tags',
    prefix:'category-tag',label:'Tags',placeholder:'Selecione tags',selectedCountLabel:'tags selecionadas',
    emptyMessage:'Nenhuma tag cadastrada.',noResultsMessage:'Nenhuma tag encontrada.',loadingMessage:'A carregar tags…',unnamedLabel:'Tag sem nome'}
} as const;

export type TagCategoryOwner=keyof typeof tagCategoryAssociations;

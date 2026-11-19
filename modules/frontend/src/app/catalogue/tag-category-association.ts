/** The same association viewed from either creation form; no nested create payloads. */
export const tagCategoryAssociations={
  tags:{owner:'tags',related:'tag_categories',ownerKey:'id_tags',relatedKey:'id_tag_categories',
    prefix:'tag-category',label:'Tag Categories',placeholder:'Select categories',selectedCountLabel:'categories selected',
    emptyMessage:'No categories created yet.',noResultsMessage:'No categories found.',loadingMessage:'Loading categories…',unnamedLabel:'Unnamed category'},
  tag_categories:{owner:'tag_categories',related:'tags',ownerKey:'id_tag_categories',relatedKey:'id_tags',
    prefix:'category-tag',label:'Tags',placeholder:'Select tags',selectedCountLabel:'tags selected',
    emptyMessage:'No tags created yet.',noResultsMessage:'No tags found.',loadingMessage:'Loading tags…',unnamedLabel:'Unnamed tag'}
} as const;

export type TagCategoryOwner=keyof typeof tagCategoryAssociations;

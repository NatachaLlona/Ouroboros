export type Resource = 'platforms' | 'tags' | 'work_classifications';
export interface PlatformDraft {
  platform_name: string; platform_is_paid: boolean; platform_is_episodes: boolean; platform_is_duration_time: boolean;
  price_amount: string; price_currency: string; application: boolean; website: boolean; link: boolean; platform_url: string;
}
export interface TagDraft { tag_name: string; display_name_tags: string; description_tags: string; }
export interface ClassificationDraft { work_classification_name: string; display_name_work_classifications: string; description_work_classifications: string; tier: string; }
export const emptyPlatform = (): PlatformDraft => ({ platform_name: '', platform_is_paid: false, platform_is_episodes: false, platform_is_duration_time: false, price_amount: '', price_currency: '', application: false, website: false, link: false, platform_url: '' });
export const emptyTag = (): TagDraft => ({ tag_name: '', display_name_tags: '', description_tags: '' });
export const emptyClassification = (): ClassificationDraft => ({ work_classification_name: '', display_name_work_classifications: '', description_work_classifications: '', tier: '' });
export function platformPayload(value: PlatformDraft) {
  return { platform_name: value.platform_name, platform_is_paid: value.platform_is_paid, platform_is_episodes: value.platform_is_episodes,
    platform_is_duration_time: value.platform_is_duration_time, price_amount: value.price_amount || null, price_currency: value.price_currency || null,
    platform_access_types: (['application', 'website', 'link'] as const).filter(type => value[type]), platform_url: value.platform_url || null };
}
export function tagPayload(value: TagDraft) { return { ...value, description_tags: value.description_tags || null }; }
export function classificationPayload(value: ClassificationDraft) {
  return { work_classification_name: value.work_classification_name, display_name_work_classifications: value.display_name_work_classifications,
    description_work_classifications: value.description_work_classifications || null,
    ...(value.tier === '' ? {} : { tier: Number(value.tier) }) };
}

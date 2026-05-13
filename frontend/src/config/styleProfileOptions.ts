/**
 * Gender/style-identity keyed option sets for body types, fits, and size fields.
 * Keys align with API + UserStyleProfile.gender.
 */
export type StyleIdentityKey = 'male' | 'female' | 'non_binary' | 'prefer_not_to_say' | 'custom'

export type SizeFieldType = 'text' | 'number'

export interface SizeFieldDef {
  key: string
  label: string
  type: SizeFieldType
  placeholder: string
  optional?: boolean
}

export interface StyleIdentityOption {
  id: StyleIdentityKey
  label: string
}

export const STYLE_IDENTITY_OPTIONS: StyleIdentityOption[] = [
  { id: 'male', label: 'Male' },
  { id: 'female', label: 'Female' },
  { id: 'non_binary', label: 'Non-binary' },
  { id: 'prefer_not_to_say', label: 'Prefer not to say' },
  { id: 'custom', label: 'Custom' },
]

export const STYLE_PROFILE_OPTIONS: Record<
  StyleIdentityKey,
  { bodyTypes: string[]; fitPreferences: string[]; sizeFields: SizeFieldDef[] }
> = {
  male: {
    bodyTypes: [
      'Slim', 'Athletic', 'Average', 'Broad shoulders', 'Tall', 'Short', 'Plus size',
      'Rectangle', 'Inverted triangle', 'Prefer not to say', 'Custom',
    ],
    fitPreferences: [
      'Slim fit', 'Regular fit', 'Relaxed fit', 'Oversized', 'Tailored fit', 'Loose fit',
      'Athletic fit', 'Stretch fit', 'Prefer different fits by category',
    ],
    sizeFields: [
      { key: 'tops_size', label: 'Tops size', type: 'text', placeholder: 'e.g. M' },
      { key: 'shirt_size', label: 'Shirt size', type: 'text', placeholder: 'e.g. 15½' },
      { key: 'tshirt_size', label: 'T-shirt size', type: 'text', placeholder: 'e.g. M' },
      { key: 'jacket_size', label: 'Jacket size', type: 'text', placeholder: 'e.g. 40R' },
      { key: 'bottoms_size', label: 'Bottoms size', type: 'text', placeholder: 'e.g. 32' },
      { key: 'waist_size', label: 'Waist size', type: 'text', placeholder: 'e.g. 32' },
      { key: 'inseam', label: 'Inseam', type: 'text', placeholder: 'e.g. 32', optional: true },
      { key: 'shoe_size', label: 'Shoe size', type: 'text', placeholder: 'US 10' },
      { key: 'neck_size', label: 'Neck size', type: 'text', placeholder: 'Optional', optional: true },
      { key: 'sleeve_length', label: 'Sleeve length', type: 'text', placeholder: 'Optional', optional: true },
    ],
  },
  female: {
    bodyTypes: [
      'Slim', 'Athletic', 'Average', 'Curvy', 'Petite', 'Tall', 'Plus size',
      'Pear shape', 'Apple shape', 'Hourglass', 'Rectangle', 'Inverted triangle',
      'Prefer not to say', 'Custom',
    ],
    fitPreferences: [
      'Slim fit', 'Regular fit', 'Relaxed fit', 'Oversized', 'Tailored fit', 'Loose fit',
      'Stretch fit', 'High-waist fit', 'Cropped fit', 'Flowy fit', 'Bodycon fit',
      'Prefer different fits by category',
    ],
    sizeFields: [
      { key: 'tops_size', label: 'Tops size', type: 'text', placeholder: 'e.g. M' },
      { key: 'blouse_size', label: 'Blouse size', type: 'text', placeholder: 'e.g. 8' },
      { key: 'dress_size', label: 'Dress size', type: 'text', placeholder: 'e.g. 8' },
      { key: 'bottoms_size', label: 'Bottoms size', type: 'text', placeholder: 'e.g. 8' },
      { key: 'jeans_size', label: 'Jeans size', type: 'text', placeholder: 'e.g. 28' },
      { key: 'waist_size', label: 'Waist size', type: 'text', placeholder: 'e.g. 28' },
      { key: 'hip_size', label: 'Hip size', type: 'text', placeholder: 'Optional', optional: true },
      { key: 'inseam', label: 'Inseam', type: 'text', placeholder: 'e.g. 30' },
      { key: 'jacket_size', label: 'Jacket size', type: 'text', placeholder: 'e.g. S' },
      { key: 'shoe_size', label: 'Shoe size', type: 'text', placeholder: 'US 8' },
    ],
  },
  non_binary: {
    bodyTypes: [
      'Slim', 'Athletic', 'Average', 'Curvy', 'Broad shoulders', 'Petite', 'Tall', 'Plus size',
      'Pear shape', 'Apple shape', 'Hourglass', 'Rectangle', 'Inverted triangle',
      'Prefer not to say', 'Custom',
    ],
    fitPreferences: [
      'Slim fit', 'Regular fit', 'Relaxed fit', 'Oversized', 'Tailored fit', 'Loose fit',
      'Stretch fit', 'Androgynous fit', 'Structured fit', 'Flowy fit',
      'Prefer different fits by category',
    ],
    sizeFields: [
      { key: 'tops_size', label: 'Tops size', type: 'text', placeholder: 'e.g. M' },
      { key: 'shirt_size', label: 'Shirt size', type: 'text', placeholder: 'e.g. M' },
      { key: 'tshirt_size', label: 'T-shirt size', type: 'text', placeholder: 'e.g. M' },
      { key: 'jacket_size', label: 'Jacket size', type: 'text', placeholder: 'e.g. M' },
      { key: 'dress_size', label: 'Dress size', type: 'text', placeholder: 'Optional', optional: true },
      { key: 'bottoms_size', label: 'Bottoms size', type: 'text', placeholder: 'e.g. 30' },
      { key: 'waist_size', label: 'Waist size', type: 'text', placeholder: 'e.g. 30' },
      { key: 'hip_size', label: 'Hip size', type: 'text', placeholder: 'Optional', optional: true },
      { key: 'inseam', label: 'Inseam', type: 'text', placeholder: 'e.g. 30' },
      { key: 'shoe_size', label: 'Shoe size', type: 'text', placeholder: 'US 9' },
    ],
  },
  prefer_not_to_say: {
    bodyTypes: [
      'Slim', 'Athletic', 'Average', 'Curvy', 'Broad shoulders', 'Petite', 'Tall', 'Plus size',
      'Rectangle', 'Prefer not to say', 'Custom',
    ],
    fitPreferences: [
      'Slim fit', 'Regular fit', 'Relaxed fit', 'Oversized', 'Tailored fit', 'Loose fit',
      'Stretch fit', 'Prefer different fits by category',
    ],
    sizeFields: [
      { key: 'tops_size', label: 'Tops size', type: 'text', placeholder: 'e.g. M' },
      { key: 'bottoms_size', label: 'Bottoms size', type: 'text', placeholder: 'e.g. M' },
      { key: 'jacket_size', label: 'Jacket size', type: 'text', placeholder: 'e.g. M' },
      { key: 'waist_size', label: 'Waist size', type: 'text', placeholder: 'e.g. 32' },
      { key: 'inseam', label: 'Inseam', type: 'text', placeholder: 'Optional', optional: true },
      { key: 'shoe_size', label: 'Shoe size', type: 'text', placeholder: 'US 9' },
    ],
  },
  custom: {
    bodyTypes: [
      'Slim', 'Athletic', 'Average', 'Curvy', 'Broad shoulders', 'Petite', 'Tall', 'Plus size',
      'Pear shape', 'Apple shape', 'Hourglass', 'Rectangle', 'Inverted triangle',
      'Prefer not to say', 'Custom',
    ],
    fitPreferences: [
      'Slim fit', 'Regular fit', 'Relaxed fit', 'Oversized', 'Tailored fit', 'Loose fit',
      'Athletic fit', 'Stretch fit', 'High-waist fit', 'Cropped fit', 'Flowy fit', 'Bodycon fit',
      'Androgynous fit', 'Structured fit', 'Prefer different fits by category',
    ],
    sizeFields: [
      { key: 'tops_size', label: 'Tops size', type: 'text', placeholder: 'e.g. M' },
      { key: 'shirt_size', label: 'Shirt size', type: 'text', placeholder: 'e.g. M' },
      { key: 'blouse_size', label: 'Blouse size', type: 'text', placeholder: 'e.g. 8' },
      { key: 'dress_size', label: 'Dress size', type: 'text', placeholder: 'e.g. 8' },
      { key: 'jacket_size', label: 'Jacket size', type: 'text', placeholder: 'e.g. M' },
      { key: 'bottoms_size', label: 'Bottoms size', type: 'text', placeholder: 'e.g. 32' },
      { key: 'jeans_size', label: 'Jeans size', type: 'text', placeholder: 'e.g. 30' },
      { key: 'waist_size', label: 'Waist size', type: 'text', placeholder: 'e.g. 32' },
      { key: 'hip_size', label: 'Hip size', type: 'text', placeholder: 'Optional', optional: true },
      { key: 'inseam', label: 'Inseam', type: 'text', placeholder: 'e.g. 30' },
      { key: 'shoe_size', label: 'Shoe size', type: 'text', placeholder: 'US 9' },
      { key: 'neck_size', label: 'Neck size', type: 'text', placeholder: 'Optional', optional: true },
      { key: 'sleeve_length', label: 'Sleeve length', type: 'text', placeholder: 'Optional', optional: true },
    ],
  },
}

/** Shared catalogues (not gender-gated) */
export const STYLE_TAGS = [
  'Casual', 'Business casual', 'Formal', 'Streetwear', 'Minimal', 'Classic', 'Sporty', 'Luxury',
  'Trendy', 'Traditional', 'Travel-friendly', 'Comfort-first', 'Sustainable', 'Occasion-based styling',
]

export const OCCASION_PREFS = [
  'Work', 'College', 'Gym', 'Travel', 'Date night', 'Parties', 'Weddings', 'Interviews',
  'Daily casual', 'Outdoor activities', 'Religious/cultural events', 'Business meetings',
]

export const CLIMATE_PREFS = [
  'Warm weather preference', 'Cold weather layering preference', 'Rain-friendly outfits',
  'Breathable fabrics', 'Avoid heavy fabrics', 'Sensitive to tight clothes', 'Comfortable shoes priority',
]

export const AGE_RANGES = [
  { id: 'under_18', label: 'Under 18' },
  { id: '18_24', label: '18–24' },
  { id: '25_34', label: '25–34' },
  { id: '35_44', label: '35–44' },
  { id: '45_plus', label: '45+' },
  { id: 'prefer_not', label: 'Prefer not to say' },
]

export function optionsForGender(g: StyleIdentityKey | null): (typeof STYLE_PROFILE_OPTIONS)[StyleIdentityKey] {
  if (!g) return STYLE_PROFILE_OPTIONS.prefer_not_to_say
  return STYLE_PROFILE_OPTIONS[g] ?? STYLE_PROFILE_OPTIONS.custom
}

import type { ClosetItem, Outfit, ChatMessage, OutfitSuggestion } from '@/types'

export const DUMMY_ITEMS: ClosetItem[] = [
  {
    id: 'item-001', user_id: "demo-user-001", name: 'White Oxford Shirt', category: 'tops',
    color: 'White', color_hex: '#FFFFFF', fabric: 'Cotton', pattern: 'Solid',
    brand: 'Uniqlo', size: 'M', price: 39.99,
    image_url: 'https://images.unsplash.com/photo-1596755094514-f87e34085b2c?w=400&q=80',
    tags: ['office', 'classic'], wear_count: 12, last_worn: '2026-04-10',
    season: 'all-season', occasion: ['work', 'casual'], eco_score: 8,
    is_favorite: true, notes: 'Machine wash cold', created_at: '2026-01-15T10:00:00Z',
  },
  {
    id: 'item-002', user_id: "demo-user-001", name: 'Navy Slim Chinos', category: 'bottoms',
    color: 'Navy', color_hex: '#1B2A4A', fabric: 'Cotton blend', pattern: 'Solid',
    brand: 'J.Crew', size: '32x30', price: 79.50,
    image_url: 'https://images.unsplash.com/photo-1594938298603-c8148c4b3ba8?w=400&q=80',
    tags: ['versatile'], wear_count: 18, last_worn: '2026-04-14',
    season: 'all-season', occasion: ['work', 'casual', 'smart-casual'], eco_score: 6,
    is_favorite: true, notes: undefined, created_at: '2026-01-20T10:00:00Z',
  },
  {
    id: 'item-003', user_id: "demo-user-001", name: 'Black Turtleneck', category: 'tops',
    color: 'Black', color_hex: '#1A1A1A', fabric: 'Merino Wool', pattern: 'Solid',
    brand: 'COS', size: 'M', price: 69.00,
    image_url: 'https://images.unsplash.com/photo-1618354691373-d851c5c3a990?w=400&q=80',
    tags: ['minimal', 'winter'], wear_count: 9, last_worn: '2026-03-28',
    season: 'winter', occasion: ['casual', 'party', 'work'], eco_score: 9,
    is_favorite: false, notes: 'Dry clean recommended', created_at: '2026-02-01T10:00:00Z',
  },
  {
    id: 'item-004', user_id: "demo-user-001", name: 'White Sneakers', category: 'shoes',
    color: 'White', color_hex: '#F5F5F5', fabric: 'Leather', pattern: 'Solid',
    brand: 'Common Projects', size: 'US 10', price: 310.00,
    image_url: 'https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=400&q=80',
    tags: ['minimal', 'everyday'], wear_count: 30, last_worn: '2026-04-16',
    season: 'all-season', occasion: ['casual', 'smart-casual'], eco_score: 5,
    is_favorite: true, notes: undefined, created_at: '2025-12-10T10:00:00Z',
  },
  {
    id: 'item-005', user_id: "demo-user-001", name: 'Beige Trench Coat', category: 'outerwear',
    color: 'Beige', color_hex: '#D4B896', fabric: 'Cotton gabardine', pattern: 'Solid',
    brand: 'Burberry', size: 'M', price: 1890.00,
    image_url: 'https://images.unsplash.com/photo-1591047139829-d91aecb6caea?w=400&q=80',
    tags: ['classic', 'autumn'], wear_count: 7, last_worn: '2026-03-15',
    season: 'autumn', occasion: ['work', 'formal', 'smart-casual'], eco_score: 7,
    is_favorite: true, notes: undefined, created_at: '2025-10-05T10:00:00Z',
  },
  {
    id: 'item-006', user_id: "demo-user-001", name: 'Floral Midi Dress', category: 'dresses',
    color: 'Floral', color_hex: '#E8A5B5', fabric: 'Linen', pattern: 'Floral',
    brand: 'Reformation', size: 'S', price: 148.00,
    image_url: 'https://images.unsplash.com/photo-1572804013309-59a88b7e92f1?w=400&q=80',
    tags: ['summer', 'feminine'], wear_count: 5, last_worn: '2026-04-05',
    season: 'summer', occasion: ['casual', 'party', 'date'], eco_score: 9,
    is_favorite: false, notes: undefined, created_at: '2026-03-20T10:00:00Z',
  },
  {
    id: 'item-007', user_id: "demo-user-001", name: 'Charcoal Blazer', category: 'outerwear',
    color: 'Charcoal', color_hex: '#3D3D3D', fabric: 'Wool blend', pattern: 'Solid',
    brand: 'Zara', size: 'M', price: 120.00,
    image_url: 'https://images.unsplash.com/photo-1507679799987-c73779587ccf?w=400&q=80',
    tags: ['formal', 'office'], wear_count: 14, last_worn: '2026-04-12',
    season: 'all-season', occasion: ['work', 'formal'], eco_score: 5,
    is_favorite: false, notes: undefined, created_at: '2026-01-08T10:00:00Z',
  },
  {
    id: 'item-008', user_id: "demo-user-001", name: 'Dark Wash Jeans', category: 'bottoms',
    color: 'Dark Blue', color_hex: '#1C3561', fabric: 'Denim', pattern: 'Solid',
    brand: 'Levi\'s', size: '32x32', price: 89.50,
    image_url: 'https://images.unsplash.com/photo-1604176354204-9268737828e4?w=400&q=80',
    tags: ['everyday', 'versatile'], wear_count: 25, last_worn: '2026-04-15',
    season: 'all-season', occasion: ['casual', 'smart-casual'], eco_score: 4,
    is_favorite: true, notes: undefined, created_at: '2025-11-22T10:00:00Z',
  },
  {
    id: 'item-009', user_id: "demo-user-001", name: 'Silk Slip Dress', category: 'dresses',
    color: 'Champagne', color_hex: '#F7E7CE', fabric: 'Silk', pattern: 'Solid',
    brand: 'Vince', size: 'XS', price: 295.00,
    image_url: 'https://images.unsplash.com/photo-1585487000160-6ebcfceb0d03?w=400&q=80',
    tags: ['evening', 'luxury'], wear_count: 3, last_worn: '2026-02-14',
    season: 'all-season', occasion: ['party', 'date', 'formal'], eco_score: 8,
    is_favorite: true, notes: 'Dry clean only', created_at: '2026-01-30T10:00:00Z',
  },
  {
    id: 'item-010', user_id: "demo-user-001", name: 'Tan Leather Belt', category: 'accessories',
    color: 'Tan', color_hex: '#C69A6D', fabric: 'Leather', pattern: 'Solid',
    brand: 'Anderson\'s', size: 'One size', price: 85.00,
    image_url: 'https://images.unsplash.com/photo-1553062407-98eeb64c6a62?w=400&q=80',
    tags: ['accessory', 'classic'], wear_count: 22, last_worn: '2026-04-14',
    season: 'all-season', occasion: ['work', 'casual', 'formal'], eco_score: 6,
    is_favorite: false, notes: undefined, created_at: '2025-09-15T10:00:00Z',
  },
  {
    id: 'item-011', user_id: "demo-user-001", name: 'Olive Utility Jacket', category: 'outerwear',
    color: 'Olive', color_hex: '#6B7C47', fabric: 'Cotton', pattern: 'Solid',
    brand: 'Carhartt', size: 'M', price: 110.00,
    image_url: 'https://images.unsplash.com/photo-1551028719-00167b16eac5?w=400&q=80',
    tags: ['casual', 'utility'], wear_count: 11, last_worn: '2026-03-22',
    season: 'spring', occasion: ['casual'], eco_score: 7,
    is_favorite: false, notes: undefined, created_at: '2026-02-15T10:00:00Z',
  },
  {
    id: 'item-012', user_id: "demo-user-001", name: 'White Stan Smith', category: 'shoes',
    color: 'White/Green', color_hex: '#FFFFFF', fabric: 'Leather', pattern: 'Solid',
    brand: 'Adidas', size: 'US 10', price: 90.00,
    image_url: 'https://images.unsplash.com/photo-1586525198428-d4bb2a5df74a?w=400&q=80',
    tags: ['sneaker', 'classic'], wear_count: 20, last_worn: '2026-04-11',
    season: 'all-season', occasion: ['casual', 'sport'], eco_score: 4,
    is_favorite: false, notes: undefined, created_at: '2025-08-10T10:00:00Z',
  },
  {
    id: 'item-013', user_id: "demo-user-001", name: 'Cashmere Crewneck', category: 'tops',
    color: 'Camel', color_hex: '#C69A6D', fabric: 'Cashmere', pattern: 'Solid',
    brand: 'Everlane', size: 'M', price: 188.00,
    image_url: 'https://images.unsplash.com/photo-1576566588028-4147f3842f27?w=400&q=80',
    tags: ['luxury', 'winter'], wear_count: 8, last_worn: '2026-03-05',
    season: 'winter', occasion: ['casual', 'smart-casual'], eco_score: 8,
    is_favorite: true, notes: 'Hand wash cold', created_at: '2026-01-10T10:00:00Z',
  },
]

export const DUMMY_OUTFITS: Outfit[] = [
  {
    id: 'outfit-001', name: 'Monday Work Look',
    item_ids: ['item-001', 'item-002', 'item-004'],
    occasion: 'work', weather_condition: 'sunny', temperature: 22,
    ai_explanation: 'A classic business-casual combination. The white Oxford shirt and navy chinos create a timeless pairing, elevated by clean white sneakers for a modern edge.',
    style_score: 9.1, is_saved: true,
  },
  {
    id: 'outfit-002', name: 'Weekend Minimal',
    item_ids: ['item-003', 'item-008', 'item-012'],
    occasion: 'casual', weather_condition: 'cloudy', temperature: 17,
    ai_explanation: 'The black turtleneck and dark jeans create a sleek monochromatic base, with Stan Smiths adding a casual, approachable touch. Effortlessly cool.',
    style_score: 8.7, is_saved: true,
  },
  {
    id: 'outfit-003', name: 'Evening Out',
    item_ids: ['item-009', 'item-004'],
    occasion: 'party', weather_condition: 'clear', temperature: 20,
    ai_explanation: 'The champagne silk slip dress is the star here. Paired with clean white sneakers for a modern twist on evening dressing — chic and unexpected.',
    style_score: 9.3, is_saved: false,
  },
]

export const DUMMY_CHAT: ChatMessage[] = [
  {
    id: 'msg-001', role: 'assistant',
    content: 'Hey Alex! 👋 I\'m your AI stylist. I\'ve analysed your wardrobe and I\'m ready to help you look amazing today. What can I do for you?',
    timestamp: new Date(Date.now() - 3 * 60000),
  },
  {
    id: 'msg-002', role: 'user',
    content: 'What should I wear for a business casual lunch today? It\'s around 22°C outside.',
    timestamp: new Date(Date.now() - 2 * 60000),
  },
  {
    id: 'msg-003', role: 'assistant',
    content: 'Perfect weather for a sharp look! Here are my top 3 picks from your closet for a business casual lunch at 22°C:',
    outfits: [
      {
        name: 'Classic Power Lunch',
        item_ids: ['item-001', 'item-002', 'item-004'],
        items: [DUMMY_ITEMS[0], DUMMY_ITEMS[1], DUMMY_ITEMS[3]],
        explanation: 'Your white Oxford + navy chinos is a timeless combination. Clean white sneakers keep it modern without being too casual.',
        style_score: 9.1, occasion_fit: 'Perfect for business casual', weather_fit: 'Great for 22°C',
      },
    ],
    timestamp: new Date(Date.now() - 1 * 60000),
  },
]

export const DUMMY_SUGGESTIONS: OutfitSuggestion[] = [
  {
    name: 'Office Smart',
    item_ids: ['item-007', 'item-001', 'item-002', 'item-004'],
    items: [DUMMY_ITEMS[6], DUMMY_ITEMS[0], DUMMY_ITEMS[1], DUMMY_ITEMS[3]],
    explanation: 'Charcoal blazer over the white shirt creates a sharp professional look. Navy chinos and white sneakers complete the ensemble.',
    style_score: 9.2, occasion_fit: 'Perfect for office', weather_fit: 'Ideal for mild weather',
  },
  {
    name: 'Weekend Casual',
    item_ids: ['item-003', 'item-008', 'item-012'],
    items: [DUMMY_ITEMS[2], DUMMY_ITEMS[7], DUMMY_ITEMS[11]],
    explanation: 'Black turtleneck with dark wash jeans — a cool, effortless pairing. Stan Smiths add the perfect casual touch.',
    style_score: 8.8, occasion_fit: 'Great for weekends', weather_fit: 'Perfect for cool days',
  },
  {
    name: 'Evening Chic',
    item_ids: ['item-009', 'item-010'],
    items: [DUMMY_ITEMS[8], DUMMY_ITEMS[9]],
    explanation: 'The silk slip dress speaks for itself. A minimal tan belt adds structure and elevates the silhouette for evening.',
    style_score: 9.4, occasion_fit: 'Excellent for evenings out', weather_fit: 'Best for warm evenings',
  },
]

export const COLOR_STATS = [
  { name: 'White', value: 28, fill: '#F1F5F9' },
  { name: 'Navy', value: 22, fill: '#1E3A5F' },
  { name: 'Black', value: 19, fill: '#1A1A1A' },
  { name: 'Beige', value: 14, fill: '#D4B896' },
  { name: 'Olive', value: 10, fill: '#6B7C47' },
  { name: 'Other', value: 7, fill: '#A78BFA' },
]

export const WEAR_STATS = [
  { name: 'Dark Wash Jeans', wears: 25 },
  { name: 'White Sneakers', wears: 22 },
  { name: 'Tan Belt', wears: 22 },
  { name: 'Stan Smith', wears: 20 },
  { name: 'Navy Chinos', wears: 18 },
  { name: 'White Oxford', wears: 12 },
  { name: 'Charcoal Blazer', wears: 14 },
  { name: 'Turtleneck', wears: 9 },
]

export const CATEGORY_STATS = [
  { category: 'Tops', count: 3 },
  { category: 'Bottoms', count: 2 },
  { category: 'Shoes', count: 2 },
  { category: 'Outerwear', count: 3 },
  { category: 'Dresses', count: 2 },
  { category: 'Accessories', count: 1 },
]

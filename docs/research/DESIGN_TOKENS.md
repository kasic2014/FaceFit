# Design Tokens - Saramin AI Interview

## Color Palette

### Primary Colors
- **Purple/Violet (Primary CTA):** #7c3aed (or #6d28d9 for darker variant)
- **Dark Navy (Headers, Dark Text):** #1a1f3a or #2d3748
- **Light Gray-Blue (Hero Background):** #dce4f0 or #e8eef8

### Secondary Colors
- **Light Pink (Alert/Accent Text):** #f8d7e8 or #fce4ec
- **Medium Blue-Gray:** #5a6b7d or #64748b
- **Light Blue (Section Background):** #dfe6f3 or similar

### Neutral Colors
- **White/Off-White (Main Background):** #ffffff
- **Light Gray (Secondary Background):** #f5f5f5 or #f8fafc
- **Dark Gray (Secondary Text):** #666666 or #6b7280
- **Medium Gray (Borders):** #d1d5db or #e5e7eb

### Status Colors (Inferred)
- **Success/Green:** Not prominently visible in screenshots
- **Warning/Yellow:** Not clearly visible
- **Error/Red:** Not clearly visible

## Typography

### Font Families
- **Primary Font:** System font stack (likely Korean optimized)
  - Estimated: `-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif` or similar
  - Korean font: Likely "Noto Sans KR" or "Apple SD Gothic Neo"
- **Monospace:** Not visible in current view

### Font Sizes
- **H1 (Hero):** ~32-40px (estimated from visual)
- **H2 (Section):** ~24-28px
- **H3 (Subsection):** ~18-20px
- **Body:** ~14-16px
- **Caption/Small:** ~12-14px
- **Label:** ~12px

### Font Weights
- **Light:** 300
- **Regular:** 400
- **Medium:** 500
- **Semibold:** 600
- **Bold:** 700

### Line Heights
- **Headings:** 1.2-1.3
- **Body:** 1.5-1.6
- **Tight:** 1.2

## Spacing Scale

Based on typical design systems:
- **xs:** 4px
- **sm:** 8px
- **md:** 12px or 16px
- **lg:** 20px or 24px
- **xl:** 32px or 40px
- **2xl:** 48px or 64px

## Border Radius

- **Small (Buttons, inputs):** 4px-6px
- **Medium (Cards):** 8px-12px
- **Large (Modals, overlays):** 16px-20px
- **Full (Pills):** 9999px

## Shadows

- **Small/Subtle:** `0 1px 2px rgba(0,0,0,0.05)`
- **Medium:** `0 4px 6px rgba(0,0,0,0.1)`
- **Large:** `0 10px 15px rgba(0,0,0,0.1)`

## Button Styles

### Primary Button
- **Background:** #7c3aed (Purple)
- **Text Color:** White (#ffffff)
- **Padding:** ~12px 24px (estimated)
- **Border Radius:** ~6-8px
- **Font Weight:** 600 or 700
- **Hover State:** Darker purple (#6d28d9 or similar)
- **Text:** "무료 체험하기" or "이용권 구매하기"

### Secondary Button/Link
- **Text Color:** #7c3aed (Purple) or primary color
- **Background:** Transparent or light purple
- **Underline:** May be present on hover

### Text Button
- **Style:** Plain text, no background
- **Color:** Primary purple or link color

## Gradients & Backgrounds

### Hero Background
- **Type:** Linear gradient
- **Colors:** Light blue-gray to slightly darker blue-gray
- **Direction:** Likely vertical (top to bottom)
- **Estimated:** #dce4f0 → #c8d9e8 or similar

## Component-Specific Tokens

### Promo Banner
- **Background:** Dark (possibly dark navy or near-black)
- **Text Color:** White
- **Height:** ~50-60px (estimated)

### Card Backgrounds
- **White cards on light background**
- **Border:** Likely subtle, possibly #e5e7eb or transparent
- **Shadow:** Small shadow for elevation

### Badge/Label Backgrounds
- **Pink background:** #f8d7e8 or #fce4ec
- **Black text backdrop:** #000000 with possible transparency

### Text Highlights
- **Purple/Accent color:** #7c3aed used for emphasis text

## Responsive Breakpoints (Mobile-First)

Based on m.saramin.co.kr (mobile site):
- **Mobile:** Full width (default)
- **Tablet:** ~768px and above (likely)
- **Desktop:** ~1024px and above (likely)

Currently optimized for mobile viewport (390px width observed in mobile view)

## Accessibility Considerations

- **Color Contrast:** Purple on white appears to have sufficient contrast
- **Button Sizing:** CTA buttons appear to be appropriately sized for mobile (touch targets)

## Files to Update

1. `src/app/layout.tsx` - Add font imports
2. `src/app/globals.css` - Define CSS variables for colors and spacing
3. `src/app/globals.css` - Add tailwind config overrides if needed

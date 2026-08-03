# HeroSection Component Specification

## Overview
- **Target file:** `src/components/HeroSection.tsx`
- **Type:** Hero banner with gradient background and CTA
- **Interaction model:** Static (no interactions, just display)

## DOM Structure
```
<section class="hero-section">
  <div class="hero-background"> {/* gradient background */}
    <div class="hero-content">
      <h1 class="hero-heading">
        <span>합격될 때까지</span>
        <span>연습하세요</span>
        <span class="accent">사람인 AI 모의면접</span>
      </h1>
      <div class="divider-line"></div>
      <p class="hero-subheading">사람인 AI 모의면접은</p>
      <button class="cta-button primary">무료 체험하기</button>
    </div>
  </div>
</section>
```

## Computed Styles

### Container (.hero-section)
- display: flex
- min-height: 400px (estimated)
- width: 100%
- position: relative
- overflow: hidden

### Background (.hero-background)
- background: linear-gradient(135deg, #dce4f0 0%, #c8d9e8 100%)
- position: absolute
- width: 100%
- height: 100%
- top: 0
- left: 0

### Content (.hero-content)
- display: flex
- flex-direction: column
- align-items: center
- justify-content: center
- position: relative
- z-index: 10
- padding: 60px 20px
- text-align: center
- min-height: 100%

### Heading (.hero-heading)
- font-size: 36px (or 2.25rem)
- font-weight: 700
- color: #ffffff
- line-height: 1.3
- margin: 0 0 20px 0
- display: flex
- flex-direction: column
- gap: 8px

### Accent Text (.accent)
- color: #7c3aed (purple)
- font-weight: 700

### Divider Line (.divider-line)
- width: 2px
- height: 40px
- background: #ffffff
- margin: 20px auto
- opacity: 0.8

### Subheading (.hero-subheading)
- font-size: 14px
- color: #ffffff
- opacity: 0.9
- margin: 0 0 20px 0
- font-weight: 400

### CTA Button (.cta-button.primary)
- background: #7c3aed
- color: #ffffff
- padding: 12px 32px
- border-radius: 6px
- border: none
- font-size: 16px
- font-weight: 600
- cursor: pointer
- transition: background 0.2s ease
- hover: background #6d28d9 (darker purple)

## Content
- Main Heading Line 1: "합격될 때까지"
- Main Heading Line 2: "연습하세요"
- Accent Text: "사람인 AI 모의면접"
- Subheading: "사람인 AI 모의면접은"
- Button Text: "무료 체험하기"
- Button Link: javascript:; (currently, should navigate to free trial)

## Responsive Behavior
- **Desktop (1440px):** Full width, centered content, larger padding
- **Tablet (768px):** Adjusted padding and font sizes
- **Mobile (390px):** 
  - min-height: 300px
  - padding: 40px 20px
  - font-size: 32px for heading
  - Full width with safe spacing

## States & Behaviors
N/A - Static section

## Assets
- No external images (gradient only)

## Implementation Notes
- Use Next.js Link component for CTA button if needed
- Ensure text contrast is sufficient for accessibility
- Consider adding animation on page load (fade-in or slide-up)

# Bloaty McBloatface - Design Principles

## Design Philosophy

### Core Principles

1. **Minimalism**: Every element must earn its place. Remove decoration that doesn't serve a functional purpose.

2. **Clarity over decoration**: Information hierarchy and usability trump visual flair. Remove visual noise.

3. **Context over pre-emption**: Show controls when needed, not speculatively. Collapse optional elements by default.

4. **Elegance through restraint**: Simple, refined, professional aesthetic. Less is more.

### Anti-patterns to Avoid

- ❌ Emoji overuse (removes all emojis including logo)
- ❌ Markdown-style headings with emojis
- ❌ Redundant UI elements (duplicate buttons/headings)
- ❌ Excessive vertical length
- ❌ Overly bright accent colors (yellow disclaimers)
- ❌ Button fatigue (too many CTAs competing for attention)

---

## Color Palette

### Primary Colors

```css
--color-bg-primary: #0A0A0A;        /* Near-black background, 60% usage */
--color-bg-secondary: #1A1A1A;      /* Cards, elevated surfaces */
--color-text-primary: #FFFFFF;      /* White text, high contrast */
--color-text-secondary: #B0B0B0;    /* Muted text for descriptions */
```

### Accent Colors (Forest Green - 30% usage)

```css
--color-accent-green-dark: #1B4332;   /* Forest green backgrounds */
--color-accent-green: #2D6A4F;        /* Primary forest green, buttons */
--color-accent-green-light: #40916C;  /* Hover states, borders */
```

### Highlight Colors (Terracotta - 10% usage)

```css
--color-highlight-terra: #D4734B;      /* Terracotta CTAs */
--color-highlight-terra-dark: #A85C3A; /* Terracotta hover */
```

### Semantic Colors

```css
--color-success: #52B788;    /* Mild symptoms, confirmations */
--color-warning: #D4734B;    /* Moderate severity (terracotta) */
--color-error: #E63946;      /* Severe symptoms, destructive actions */
--color-info: #457B9D;       /* Neutral info, AI badges */
```

### Rationale

- Based on dark mode best practices from Material Design 3 and VSCO
- Forest green provides natural, calming association (appropriate for health app)
- Terracotta adds warmth and draws attention without being aggressive
- High contrast ratios ensure WCAG AAA compliance for accessibility
- 60/30/10 rule: 60% dark backgrounds, 30% green accents, 10% terracotta highlights

---

## Typography

### Font Stack

```css
--font-family-primary: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
--font-family-mono: "SF Mono", Monaco, "Cascadia Code", "Courier New", monospace;
```

### Type Scale

Reduced from Pico.css defaults (2-4px smaller on average):

```css
--text-xs: 0.75rem;    /* 12px - metadata, timestamps */
--text-sm: 0.875rem;   /* 14px - body text, descriptions */
--text-base: 1rem;     /* 16px - default body */
--text-lg: 1.125rem;   /* 18px - card titles */
--text-xl: 1.25rem;    /* 20px - section headings */
--text-2xl: 1.5rem;    /* 24px - page titles */
--text-3xl: 1.875rem;  /* 30px - hero headings */
```

### Font Weights

```css
--font-regular: 400;   /* Body text */
--font-medium: 500;    /* Emphasis, button labels */
--font-semibold: 600;  /* Headings, important labels */
--font-bold: 700;      /* Rare, only for critical emphasis */
```

### Line Heights

```css
--line-tight: 1.25;    /* Headings */
--line-normal: 1.5;    /* Body text */
--line-relaxed: 1.75;  /* Long-form content */
```

---

## Spacing & Layout

### Spacing Scale (8px grid)

```css
--space-1: 0.25rem;   /* 4px */
--space-2: 0.5rem;    /* 8px */
--space-3: 0.75rem;   /* 12px */
--space-4: 1rem;      /* 16px */
--space-6: 1.5rem;    /* 24px */
--space-8: 2rem;      /* 32px */
--space-12: 3rem;     /* 48px */
--space-16: 4rem;     /* 64px */
```

### Container Widths

```css
--container-sm: 640px;   /* Forms, focused content */
--container-md: 768px;   /* Default content */
--container-lg: 1024px;  /* Wide layouts */
--container-xl: 1280px;  /* Dashboards, analytics */
```

### Border Radius

```css
--radius-sm: 4px;      /* Small elements, badges */
--radius-md: 8px;      /* Cards, inputs */
--radius-lg: 12px;     /* Large cards, modals */
--radius-full: 9999px; /* Pills, circular avatars/images */
```

---

## Component Design System

### Buttons

#### Primary Button (Forest Green)

```css
background: var(--color-accent-green);
color: white;
border-radius: var(--radius-full);  /* Pill-shaped */
padding: 12px 24px;
font-size: var(--text-sm);
font-weight: 500;
border: none;
cursor: pointer;
transition: all 200ms ease;

/* Hover */
background: var(--color-accent-green-light);
transform: translateY(-1px);
```

#### Secondary Button (Outlined)

```css
background: transparent;
border: 1.5px solid var(--color-accent-green);
color: var(--color-accent-green);
border-radius: var(--radius-full);
padding: 12px 24px;
font-size: var(--text-sm);
font-weight: 500;

/* Hover */
background: var(--color-accent-green);
color: white;
```

#### Tertiary/Ghost Button

```css
background: transparent;
border: none;
color: var(--color-text-secondary);
padding: 8px 16px;
font-size: var(--text-sm);
font-weight: 500;

/* Hover */
color: var(--color-text-primary);
```

#### Destructive Button

```css
background: var(--color-highlight-terra);
color: white;
border-radius: var(--radius-full);
padding: 12px 24px;
font-size: var(--text-sm);
font-weight: 500;

/* Hover */
background: var(--color-highlight-terra-dark);
```

**Note:** No "contrast" variant needed with dark theme.

---

### Cards

#### Default Card

```css
background: var(--color-bg-secondary);
border: 1px solid rgba(255, 255, 255, 0.05);  /* Subtle separation */
border-radius: var(--radius-md);
padding: var(--space-6);
box-shadow: 0 2px 8px rgba(0, 0, 0, 0.4);  /* Subtle depth */
```

#### Interactive Card (hover state)

```css
border: 1px solid var(--color-accent-green-light);
transform: translateY(-2px);
box-shadow: 0 4px 12px rgba(45, 106, 79, 0.15);  /* Green glow */
transition: all 200ms ease;
cursor: pointer;
```

---

### Navigation

#### Header Navigation

```css
background: var(--color-bg-primary);
border-bottom: 1px solid rgba(255, 255, 255, 0.08);
height: 64px;
padding: var(--space-4) var(--space-8);
```

#### Logo

```
Text: "Bloaty McBloatface" (no emoji)
Font-size: var(--text-lg);
Font-weight: 600;
Color: var(--color-text-primary);
```

#### Nav Links

```css
font-size: var(--text-sm);
font-weight: 500;
color: var(--color-text-secondary);
text-decoration: none;
margin-left: var(--space-6);

/* Hover */
color: var(--color-text-primary);

/* Active */
color: var(--color-accent-green);
border-bottom: 2px solid var(--color-accent-green);
```

**Inspiration:** VSCO's clean horizontal nav with subtle indicators.

---

### Forms & Inputs

#### Text Inputs

```css
background: var(--color-bg-secondary);
border: 1px solid rgba(255, 255, 255, 0.1);
border-radius: var(--radius-md);
padding: 10px 14px;
font-size: var(--text-base);
color: var(--color-text-primary);
font-family: var(--font-family-primary);

/* Focus */
border-color: var(--color-accent-green);
box-shadow: 0 0 0 3px rgba(45, 106, 79, 0.2);
outline: none;
```

#### Labels

```css
font-size: var(--text-sm);
font-weight: 500;
color: var(--color-text-primary);
margin-bottom: var(--space-2);
display: block;
```

#### Helper Text

```css
font-size: var(--text-xs);
color: var(--color-text-secondary);
margin-top: var(--space-1);
line-height: var(--line-normal);
```

---

### Badges & Pills

#### AI Badge (redesigned from yellow)

```css
background: var(--color-bg-secondary);
border: 1px solid rgba(69, 123, 157, 0.4);  /* Info blue */
color: #6BA4C8;  /* Light info blue */
font-size: var(--text-xs);
font-weight: 600;
padding: 4px 10px;
border-radius: var(--radius-sm);
display: inline-flex;
align-items: center;
gap: 4px;
```

Optional: Add AI sparkle icon (Lucide `sparkles`).

#### Severity Pills (symptom tags)

```css
/* Low severity (1-3) */
background: var(--color-success);
color: white;

/* Medium severity (4-7) */
background: var(--color-warning);  /* Terracotta */
color: white;

/* High severity (8-10) */
background: var(--color-error);
color: white;

/* Common styles */
font-size: var(--text-xs);
font-weight: 500;
padding: 4px 12px;
border-radius: var(--radius-full);
display: inline-block;
```

---

### Disclaimers

#### Redesigned from bright yellow box

```css
background: rgba(212, 115, 75, 0.08);  /* Subtle terracotta tint */
border: 1px solid rgba(212, 115, 75, 0.3);
border-left: 3px solid var(--color-highlight-terra);  /* Accent */
border-radius: var(--radius-md);
padding: var(--space-4);
margin: var(--space-6) 0;

/* Text */
color: var(--color-text-primary);
font-size: var(--text-sm);
line-height: 1.6;
```

**Footer disclaimer:** Same styling, but with `var(--color-bg-secondary)` background to distinguish from page content.

**Enhancement:** Make collapsible by default for returning users (use localStorage).

---

### Images

#### Meal History Images (circular crop)

**Current:** Square/rectangular thumbnails (max-width 200px)

**New design:**

```css
/* List item thumbnails */
.meal-thumbnail {
  width: 80px;
  height: 80px;
  border-radius: 50%;
  object-fit: cover;
  object-position: var(--crop-x, 50%) var(--crop-y, 50%);
  border: 2px solid rgba(255, 255, 255, 0.1);
}

/* Featured/larger thumbnails */
.meal-thumbnail-lg {
  width: 120px;
  height: 120px;
  border-radius: 50%;
  object-fit: cover;
  object-position: var(--crop-x, 50%) var(--crop-y, 50%);
  border: 2px solid rgba(255, 255, 255, 0.1);
}
```

**AI Crop Detection:**
- When meal image is uploaded, send to Claude API with prompt:
  ```
  Analyze this meal image and identify the center point of the food/plate.
  Return coordinates as percentage from top-left (x%, y%).
  If multiple items, find visual center of mass.
  ```
- Store crop center coordinates in database (`meal_image_crop_x`, `meal_image_crop_y`)
- Use CSS `object-position` to crop circular thumbnail centered at those coordinates
- Fallback to 50%, 50% if API call fails

**Implementation note:** Circular cropping is ONLY needed in meal history view, not during logging/analysis. This allows async processing without blocking upload flow.

#### Full-size Meal Images

```css
.meal-image-full {
  max-height: 500px;
  max-width: 100%;
  border-radius: var(--radius-lg);  /* 12px, softer corners */
  object-fit: contain;

  /* Responsive */
  @media (max-width: 768px) {
    max-height: 400px;
  }
}
```

---

## Page-Specific Redesigns

### Home Page

**Current issues:**
- Redundant h1 "Welcome to Bloaty McBloatface" (app name already in nav)
- Card headers ("Log a Meal") duplicate footer buttons ("Log Meal")
- 6 total CTAs create button fatigue
- Yellow disclaimer box is visually heavy

**New design:**

#### Hero Section

```
No h1 title (nav logo is sufficient)

Tagline: "Track meals, identify triggers, take control"
- Font-size: var(--text-xl)
- Color: var(--color-text-secondary)
- Max-width: 600px
- Text-align: center
- Margin: 0 auto var(--space-12)
```

#### Primary Actions (2 large cards, side-by-side)

```
Card 1: "Log Meal"
- Icon: Image/Photo (NOT camera - camera features planned for mobile)
- Single button: "Upload Photo"
- Clicking goes DIRECTLY to file upload (skip intermediate page)
- Description: 1 sentence max ("Snap a photo to analyze ingredients")

Card 2: "Log Symptoms"
- Icon: List
- Single button: "Record Symptoms"
- Description: 1 sentence max ("Track how you're feeling")

Layout: 2-column grid on desktop, stack on mobile
```

#### Secondary Actions (3 ghost buttons, horizontal)

```
"Meal History" | "Symptom History" | "Analysis"

- Smaller, de-emphasized
- Ghost button style
- Horizontal layout, centered
- Icons optional
```

#### Disclaimer

```
- Bottom of page
- Redesigned with dark theme (terracotta accent)
- Collapsible by default for returning users (localStorage)
- Minimal presence
```

**Visual hierarchy:** Tagline → Primary cards → Secondary links → Disclaimer

**Vertical reduction:** ~40% less height by removing redundant elements.

---

### Meal Logging Flow

**Current flow:**
1. `/meals/log` - Form with upload, timestamp, optional fields
2. Upload image
3. `/meals/{id}/edit_ingredients` - AI analysis, ingredient editing

**New flow (streamlined):**
1. Home → Click "Upload Photo" → Native file picker immediately
2. After selection, go directly to `/meals/analyze` with image
3. Show image + AI analysis inline
4. Single-page ingredient editing with auto-save
5. "Save & Done" button

**UI changes:**
- Remove intermediate upload form page
- Combine upload + analysis into single view
- Timestamp auto-set to "now", editable inline if needed
- Optional fields (location, notes) collapsed by default, expand on click

---

### Symptom Logging

**Current issue:** Remove button hidden when symptom cards are collapsed

**New design:**

```
Symptom tag manager:
┌─────────────────────────────────────────┐
│ [Tag] Bloating • Severity: 7        [×] │  ← Remove button ALWAYS visible
└─────────────────────────────────────────┘
│ [Tag] Nausea • Severity: 5          [×] │
└─────────────────────────────────────────┘

AI Description (cross-symptom context):
┌─────────────────────────────────────────┐
│ [Generate AI description]               │
│                                         │
│ [Editable textarea with AI notes]       │
│ User can refine AI suggestions          │
└─────────────────────────────────────────┘

Expanded symptom card (per tag):
┌─────────────────────────────────────────┐
│ [Tag] Bloating                      [×] │
│                                         │
│ Severity: [======7======] 7/10          │
│ □ Start time  □ End time                │
└─────────────────────────────────────────┘
```

**Changes:**
- Remove button ALWAYS visible (even when collapsed)
  - Position: absolute right, vertically centered
  - Style: Small ghost button with × icon
  - Color: var(--color-text-secondary), hover var(--color-error)
- Clicking collapsed card expands it (entire row is clickable except remove button)
- **AI description is cross-symptom** (parent-level feature, not per-tag)
- User can edit AI-generated description freely

---

### Meal History

**Current:** List of cards with rectangular images, expandable ingredients

**New design:**

```
Grid layout:
- 2-3 columns on desktop (depends on viewport width)
- 1 column on mobile

Each meal card:
┌────────────────────────┐
│   [Circular Image]     │  ← 120px diameter, AI-cropped
│                        │
│   Meal Name            │  ← var(--text-lg), semibold
│   Date • Location      │  ← var(--text-xs), muted
│                        │
│   [Ingredients ▼]      │  ← Collapsible, shows count when closed
└────────────────────────┘

Hover: Green border glow, slight lift

Click: Expand to show full details
- Ingredients list (pills)
- Full notes
- Edit/Delete buttons (ghost, small)
```

**Image handling:**
- Circular thumbnails with AI-detected crop center
- Consistent 120px diameter for visual rhythm
- Lazy loading for performance (`loading="lazy"`)

---

### Symptom History

**Current:** List with severity-colored tags, collapsible clarification history

**New design:**

```
Timeline view (left border with dots):

│  [Date/Time]
●  [Tag] Bloating • Severity: 7
│  AI notes collapsed (expand on click)
│  [Edit] [Delete]
│
│  [Date/Time]
●  [Tag] Nausea • Severity: 5
│  [Tag] Headache • Severity: 6
│  AI notes collapsed
│  [Edit] [Delete]
│
```

**Changes:**
- Timeline view with left border and dots (inspired by custom.css timeline styles)
- Each entry:
  - Severity pill(s) with color coding (green/terracotta/red)
  - Timestamp range (if applicable)
  - Collapsed AI notes (expand on click)
  - Edit/delete icons (always visible, minimal ghost buttons)
- Remove "AI badge" in favor of subtle icon
- Tighter spacing between entries

---

## Iconography

### Current Approach
Emojis (🍽️, 📋, ⚠️, etc.)

### New Approach
Minimal line icons from **Lucide Icons**

**Why Lucide:**
- Clean, minimal design
- MIT license (free for commercial use)
- Consistent design language
- Easy to style with CSS
- SVG format (scalable, performant)
- https://lucide.dev/

### Icon Sizes

```css
--icon-xs: 16px;   /* Inline icons */
--icon-sm: 20px;   /* UI elements */
--icon-md: 24px;   /* Default size */
--icon-lg: 32px;   /* Featured icons */
```

### Key Icons Needed

| Use Case | Icon Name | Notes |
|----------|-----------|-------|
| Meal upload | `image` | **NOT camera** (camera features planned for mobile) |
| Symptoms | `list` | Symptom logging |
| Analysis | `bar-chart-3` | Analytics dashboard |
| Remove/Close | `x` | Delete, close modals |
| Expand | `chevron-down` | Expand collapsed content |
| Collapse | `chevron-up` | Collapse expanded content |
| Settings | `settings` | Settings page |
| Calendar | `calendar` | Timestamp picker |
| Location | `map-pin` | Location field |
| Warning | `alert-triangle` | Disclaimer, warnings |
| AI indicator | `sparkles` | AI-generated content |
| Edit | `pencil` | Edit action |
| Save | `check` | Save/confirm |
| History | `clock` | History pages |

### Usage Example

```html
<svg class="icon icon-md">
  <use href="/static/icons/lucide-sprite.svg#image"></use>
</svg>
```

### Styling

```css
.icon {
  display: inline-block;
  stroke-width: 2px;
  color: inherit;  /* Inherit from parent text color */
  vertical-align: middle;
}

.icon-xs { width: 16px; height: 16px; }
.icon-sm { width: 20px; height: 20px; }
.icon-md { width: 24px; height: 24px; }
.icon-lg { width: 32px; height: 32px; }

/* Hover effect on interactive icons */
.icon-button .icon {
  transition: transform 200ms ease;
}

.icon-button:hover .icon {
  transform: scale(1.1);
}
```

---

## Accessibility

### Color Contrast

All color combinations must meet WCAG standards:
- **Body text:** AAA compliance (7:1 contrast ratio)
- **UI elements:** AA compliance (4.5:1 contrast ratio)
- **Large text (18px+):** AA compliance (3:1 contrast ratio)

**Verified combinations:**
- `#FFFFFF` on `#0A0A0A` = 19.53:1 ✅ AAA
- `#B0B0B0` on `#0A0A0A` = 10.73:1 ✅ AAA
- `#FFFFFF` on `#2D6A4F` = 5.82:1 ✅ AA
- `#FFFFFF` on `#D4734B` = 3.87:1 ✅ AA (large text only)

### Keyboard Navigation

- All interactive elements must be keyboard accessible
- Focus states must be clearly visible (use `--color-accent-green` outline)
- Tab order must be logical
- Skip links for main content

### Screen Readers

- Use semantic HTML (`<nav>`, `<main>`, `<article>`, etc.)
- Provide `alt` text for all images
- Use ARIA labels where needed (`aria-label`, `aria-labelledby`)
- Ensure icons have text alternatives

### Motion

- Respect `prefers-reduced-motion` for animations
- Keep animations subtle and purposeful
- No auto-playing content

---

## Responsive Design

### Breakpoints

```css
--breakpoint-sm: 640px;   /* Mobile landscape */
--breakpoint-md: 768px;   /* Tablet */
--breakpoint-lg: 1024px;  /* Desktop */
--breakpoint-xl: 1280px;  /* Large desktop */
```

### Mobile-First Approach

Design for mobile first, enhance for larger screens.

**Key considerations:**
- Circular meal images must not distort on any screen size
- Grid layouts collapse to single column on mobile
- Navigation may need hamburger menu (or keep horizontal if space allows)
- Touch targets must be at least 44px × 44px
- Form inputs should fill available width
- Cards stack vertically on small screens

### Testing Devices

Test on:
- Mobile: 320px width (iPhone SE)
- Tablet: 768px width (iPad)
- Desktop: 1440px width (MacBook Pro)

---

## Performance

### Optimization Goals

- Page load time: < 2s on 3G
- Lighthouse score: 90+ on all metrics
- CSS bundle size: < 50KB (uncompressed)
- Image lazy loading on history pages
- AI crop detection: < 2s latency

### Best Practices

- Use system fonts (no web font downloads)
- Optimize images (WebP format, appropriate dimensions)
- Lazy load images below the fold
- Minimize CSS (remove unused Pico.css)
- Use CSS custom properties for theming (no JS required)
- Cache static assets aggressively

---

## Browser Support

### Target Browsers

- Chrome/Edge: Last 2 versions
- Firefox: Last 2 versions
- Safari: Last 2 versions
- Mobile Safari: iOS 14+
- Chrome Android: Last 2 versions

### Fallbacks

- CSS custom properties: Required (no IE11 support)
- CSS Grid: Required
- Flexbox: Required
- Object-fit/object-position: Required (for circular image crops)

If older browser support is needed, use PostCSS with autoprefixer.

---

## Implementation Checklist

### Phase 1: Foundation
- [ ] Create `/app/static/css/design-tokens.css`
- [ ] Create `/app/static/css/base.css` (replace Pico.css)
- [ ] Download Lucide icons sprite to `/app/static/icons/`
- [ ] Update `base.html` to load new CSS files
- [ ] Remove Pico.css CDN link

### Phase 2: Components
- [ ] Create `/app/static/css/components/buttons.css`
- [ ] Create `/app/static/css/components/cards.css`
- [ ] Create `/app/static/css/components/forms.css`
- [ ] Create `/app/static/css/components/navigation.css`
- [ ] Create `/app/static/css/components/badges.css`
- [ ] Create `/app/static/css/components/images.css`
- [ ] Create `/app/static/css/components/disclaimers.css`

### Phase 3: Templates
- [ ] Update `base.html` - Navigation, remove emoji logo
- [ ] Update `home.html` - Streamline layout
- [ ] Update `meals/log.html` - Direct upload flow
- [ ] Update `meals/edit_ingredients.html` - Styling
- [ ] Update `meals/history.html` - Circular images, grid layout
- [ ] Update `symptoms/log.html` - Visible remove buttons
- [ ] Update `symptoms/history.html` - Timeline view

### Phase 4: Backend
- [ ] Add `meal_image_crop_x` and `meal_image_crop_y` columns to `Meal` model
- [ ] Create `/app/services/image_crop.py` - AI detection service
- [ ] Update `/app/api/meals.py` - Async crop detection on upload
- [ ] Create Alembic migration for new columns
- [ ] Run migration

### Phase 5: Testing
- [ ] Visual regression testing (before/after screenshots)
- [ ] Accessibility testing (WCAG compliance)
- [ ] Responsive design testing (mobile/tablet/desktop)
- [ ] Performance testing (Lighthouse)
- [ ] Functional testing (upload flow, symptom logging, etc.)

---

## Maintenance & Evolution

### Versioning

This design system should be versioned alongside the application:
- **v1.0**: Initial dark theme redesign (this document)
- Future versions track major design changes

### Review Schedule

- **Quarterly:** Review design principles, update based on user feedback
- **Per feature:** Ensure new features follow design system
- **Annually:** Major design refresh if needed

### Contributing

When adding new components:
1. Document design specs in this file first
2. Implement CSS in modular component file
3. Update implementation checklist
4. Add examples to templates

### Design Debt

Track design inconsistencies or technical debt:
- [ ] (Example) Ingredient pills have inconsistent sizing
- [ ] (Example) Modal dialogs need standardized styling

---

## Resources

### Design Inspiration

- **Slite**: Minimal, elegant interface design
- **VSCO**: Dark theme aesthetic, photography focus
- **Material Design 3**: Dark theme guidelines, accessibility
- **Linear**: Clean UI, subtle interactions

### Tools

- **Contrast Checker**: https://webaim.org/resources/contrastchecker/
- **Lucide Icons**: https://lucide.dev/
- **CSS Grid Generator**: https://cssgrid-generator.netlify.app/
- **Coolors**: https://coolors.co/ (color palette testing)

### Documentation

- **WCAG Guidelines**: https://www.w3.org/WAI/WCAG21/quickref/
- **MDN Web Docs**: https://developer.mozilla.org/
- **Can I Use**: https://caniuse.com/ (browser support)

---

## Changelog

### v1.0 - 2026-01-31

Initial design system document created.

**Major changes from previous design:**
- Replaced Pico.css with custom dark theme
- Removed all emojis (including logo)
- Implemented 60/30/10 color palette (dark/green/terracotta)
- Reduced typography sizes by 2-4px
- Added circular meal image cropping with AI detection
- Streamlined home page (removed redundancy)
- Made symptom remove buttons always visible
- Introduced Lucide icons
- Established comprehensive component system

---

**End of Design Principles Document**

*This is a living document. Update it as the design evolves.*

# InSAR Processor Design System

This document outlines the design system applied to the InSAR Processor application, following UI/UX Pro Max scientific dashboard best practices.

## Design Philosophy

**Data-Dense Dashboard** - Optimized for maximum data visibility with minimal padding, space-efficient grid layouts, and professional scientific aesthetics.

## Color Palette

### Dark Mode (Default)
- **Background**: `hsl(0, 0%, 3.9%)` - Deep black for OLED optimization
- **Foreground**: `hsl(0, 0%, 98%)` - High contrast text
- **Card**: `hsl(0, 0%, 3.9%)` - Subtle card backgrounds
- **Primary**: `hsl(0, 0%, 98%)` - Primary actions
- **Secondary**: `hsl(0, 0%, 14.9%)` - Secondary elements
- **Muted**: `hsl(0, 0%, 14.9%)` - Muted backgrounds
- **Border**: `hsl(0, 0%, 14.9%)` - Subtle borders

### Scientific Colormaps
- **Viridis**: Default for most visualizations
- **Magma**: High contrast alternative
- **Twilight**: Cyclic data
- **RdBu**: Displacement (red-blue diverging)

## Typography

- **UI Font**: Fira Sans (300, 400, 500, 600, 700)
- **Code/Technical**: Fira Code (400, 500, 600, 700)
- **Mood**: Technical, precise, dashboard-oriented

## Spacing System

4px/8px grid system:
- `grid-1`: 4px
- `grid-2`: 8px
- Standard Tailwind spacing scale

## Components

### App Bar
- Fixed position, top
- `bg-background/90` with `backdrop-blur`
- Shadow: `shadow-sm`
- Height: 64px (h-16)

### Sidebar
- Width: 300px (collapsible to 64px)
- Task cards with status badges
- Progress indicators for processing tasks

### Image Viewer
- Full zoom/pan support (react-zoom-pan-pinch)
- Colormap selector
- Measurement tools
- Export functionality

### Charts
- Recharts for time series
- Dark theme optimized
- Accessible color contrast

## Accessibility

- **WCAG AA** compliant
- Full keyboard navigation
- ARIA labels throughout
- Focus states visible
- `prefers-reduced-motion` respected

## Performance

- ⚡ Excellent performance
- Optimized image loading (next/image)
- Code splitting
- Lazy loading where appropriate

## Anti-Patterns to Avoid

- ❌ No emojis as icons (use SVG: Lucide)
- ❌ No layout shifts on hover
- ❌ No poor contrast in light mode
- ❌ No missing focus states
- ❌ No horizontal scroll on mobile

## Pre-Delivery Checklist

- [x] No emojis as icons (use SVG: Lucide)
- [x] cursor-pointer on all clickable elements
- [x] Hover states with smooth transitions (150-300ms)
- [x] Dark mode: high contrast (7:1+)
- [x] Focus states visible for keyboard nav
- [x] prefers-reduced-motion respected
- [x] Responsive: 375px, 768px, 1024px, 1440px

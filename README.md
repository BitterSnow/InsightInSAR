# InSAR Processor v1.0

Professional InSAR processing GUI built with Next.js 14, Tailwind CSS v4, shadcn/ui, Zustand, and Recharts.

## Features

- **Modern Scientific Dashboard**: Clean, professional interface optimized for data visualization
- **Task Management**: Track multiple InSAR processing tasks with real-time status updates
- **Interactive Image Viewer**: Zoom, pan, and measure with multiple colormap options
- **Time Series Analysis**: Visualize displacement trends over time
- **Dark Mode**: Optimized dark theme for extended scientific work sessions
- **Accessibility**: Full keyboard navigation and ARIA labels throughout

## Tech Stack

- **Framework**: Next.js 14 (App Router)
- **Styling**: Tailwind CSS v4
- **UI Components**: shadcn/ui (Radix UI primitives)
- **State Management**: Zustand
- **Charts**: Recharts
- **Image Zoom/Pan**: react-zoom-pan-pinch
- **Icons**: Lucide React
- **Typography**: Fira Sans & Fira Code

## Getting Started

### Prerequisites

- Node.js 18+ 
- npm or yarn

### Installation

```bash
# Install dependencies
npm install

# Run development server
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

### Build for Production

```bash
npm run build
npm start
```

## Project Structure

```
insar-system/
├── app/
│   ├── layout.tsx          # Root layout with fonts
│   ├── page.tsx            # Main page component
│   └── globals.css         # Global styles & theme
├── components/
│   ├── ui/                 # shadcn/ui components
│   ├── app-bar.tsx         # Top toolbar
│   ├── sidebar.tsx         # Tasks sidebar
│   ├── main-content.tsx    # Main content area
│   ├── image-viewer.tsx    # Image viewer with zoom/pan
│   └── time-series-chart.tsx # Time series visualization
├── lib/
│   ├── store.ts            # Zustand state management
│   └── utils.ts            # Utility functions
└── public/                 # Static assets
```

## Usage

1. **Import Data**: Click "Import Data" button to select files/folders
2. **Monitor Tasks**: View task status in the left sidebar
3. **View Results**: Click on a completed task to view results
4. **Navigate Views**: Use tabs to switch between Amplitude, Interferogram, Coherence, Unwrapped, Displacement, and Profile views
5. **Interact**: Zoom, pan, change colormaps, and measure distances

## Design System

This project follows professional scientific dashboard best practices:

- **Data-Dense Layout**: Maximum data visibility with minimal padding
- **Dark Theme**: Optimized for extended viewing sessions
- **Accessibility**: WCAG AA compliant with keyboard navigation
- **4px/8px Grid System**: Consistent spacing throughout
- **Typography**: Fira Sans for UI, Fira Code for technical data

## License

MIT

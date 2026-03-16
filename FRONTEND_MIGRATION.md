# Frontend 代码迁移完成

## ✅ 迁移完成

所有前端代码已成功移动到 `frontend/` 文件夹，并按照常见的文件组织形式进行了重新组织。

## 📁 新的文件结构

```
frontend/
├── app/                          # Next.js App Router
│   ├── layout.tsx               # 根布局（字体加载、Toaster）
│   ├── page.tsx                 # 主页面
│   └── globals.css              # 全局样式和主题变量
│
├── components/                   # React 组件
│   ├── ui/                      # shadcn/ui 基础组件
│   │   ├── button.tsx
│   │   ├── card.tsx
│   │   ├── badge.tsx
│   │   ├── tabs.tsx
│   │   ├── select.tsx
│   │   ├── progress.tsx
│   │   ├── toast.tsx
│   │   ├── use-toast.ts
│   │   └── toaster.tsx
│   │
│   ├── layout/                  # 布局组件
│   │   ├── app-bar.tsx          # 顶部工具栏
│   │   └── sidebar.tsx          # 侧边栏（任务列表）
│   │
│   └── features/                 # 功能组件
│       ├── main-content.tsx      # 主内容区域
│       ├── image-viewer.tsx      # 图像查看器（缩放/平移）
│       └── time-series-chart.tsx # 时间序列图表
│
├── lib/                          # 工具函数和状态管理
│   ├── store.ts                 # Zustand 状态管理
│   └── utils.ts                 # 工具函数（cn 等）
│
├── public/                       # 静态资源
│
├── package.json                  # 项目依赖
├── tsconfig.json                # TypeScript 配置
├── tailwind.config.ts           # Tailwind CSS 配置
├── next.config.js               # Next.js 配置
├── postcss.config.js            # PostCSS 配置
├── .eslintrc.json               # ESLint 配置
└── README.md                     # 项目说明文档
```

## 🔄 主要变更

### 1. 组件组织方式

**之前：**
```
components/
├── ui/
├── app-bar.tsx
├── sidebar.tsx
├── main-content.tsx
├── image-viewer.tsx
└── time-series-chart.tsx
```

**现在：**
```
components/
├── ui/              # 基础 UI 组件
├── layout/          # 布局组件（AppBar, Sidebar）
└── features/        # 功能组件（MainContent, ImageViewer, TimeSeriesChart）
```

### 2. 导入路径更新

所有导入路径已更新以反映新的文件结构：

**app/page.tsx:**
```typescript
// 之前
import { AppBar } from "@/components/app-bar"
import { Sidebar } from "@/components/sidebar"
import { MainContent } from "@/components/main-content"

// 现在
import { AppBar } from "@/components/layout/app-bar"
import { Sidebar } from "@/components/layout/sidebar"
import { MainContent } from "@/components/features/main-content"
```

**components/features/main-content.tsx:**
```typescript
// 之前
import { ImageViewer } from "@/components/image-viewer"
import { TimeSeriesChart } from "@/components/time-series-chart"

// 现在
import { ImageViewer } from "@/components/features/image-viewer"
import { TimeSeriesChart } from "@/components/features/time-series-chart"
```

## 📝 文件夹说明

### `components/ui/`
shadcn/ui 基础组件库，提供可复用的 UI 基础组件（Button, Card, Badge 等）。

### `components/layout/`
应用级别的布局组件：
- **app-bar.tsx**: 顶部工具栏，包含 logo 和导入按钮
- **sidebar.tsx**: 可折叠的侧边栏，显示任务列表

### `components/features/`
业务功能组件：
- **main-content.tsx**: 主内容区域，包含标签页导航
- **image-viewer.tsx**: 图像查看器，支持缩放、平移和色图选择
- **time-series-chart.tsx**: 时间序列数据可视化组件

### `lib/`
工具函数和状态管理：
- **store.ts**: Zustand 状态管理（任务、UI 状态等）
- **utils.ts**: 工具函数（cn 用于合并 className）

## 🚀 使用方法

### 开发环境

```bash
cd frontend
npm install
npm run dev
```

### 生产构建

```bash
cd frontend
npm run build
npm start
```

## ✨ 优势

1. **清晰的职责分离**: UI 组件、布局组件和功能组件分开管理
2. **易于维护**: 相关组件组织在一起，便于查找和修改
3. **可扩展性**: 新增功能组件时，只需在 `features/` 文件夹中添加
4. **符合最佳实践**: 遵循 Next.js 和 React 社区的文件组织规范

## 📌 注意事项

- 所有导入路径使用 `@/` 别名，指向 `frontend/` 目录
- TypeScript 路径配置已更新，确保类型检查正常工作
- Tailwind CSS 配置中的 content 路径已更新

## 🔍 验证

确保所有导入路径正确：
- ✅ `@/components/ui/*` - UI 组件
- ✅ `@/components/layout/*` - 布局组件
- ✅ `@/components/features/*` - 功能组件
- ✅ `@/lib/*` - 工具和状态管理

迁移完成！所有代码已按照最佳实践组织在 `frontend/` 文件夹中。

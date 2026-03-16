# PySide6 界面美观方案对比

主要为解决「界面丑、图标/文字不清晰」等问题，在**不换技术栈（仍用 PySide6）**的前提下，可选方案如下。  
（不含 Tkinter 方案：如 sv_ttk 仅支持 Tkinter，与当前 PySide6 桌面不兼容。）

---

## 1. 方案总览

| 方案 | 类型 | 许可证 | 改造量 | 观感特点 |
|------|------|--------|--------|----------|
| **PySide6-Fluent-Widgets** | 组件库（换控件） | GPLv3（商业需购许可） | 中～高 | Win11 / Fluent 风格，图标与动效完整 |
| **qt-material** | 全局样式表（不换控件） | **BSD-2-Clause** | **低** | Material Design，多主题、深色/亮色 |
| **QtModernRedux6** | 样式 + 窗口/标题栏 | **MIT** | 低～中 | 现代深色主题，跨平台一致 |
| **PySide6-Fluent-Widgets**（仅作参考） | 见上 | 见上 | 见上 | 见上 |

---

## 2. PySide6-Fluent-Widgets（qfluentwidgets）

- **作用**：用 Fluent 风格**新控件**替换现有 QPushButton、QLineEdit 等，图标统一（FluentIcon）、动效现成。
- **优点**：整体最接近「现代桌面 UI」；按钮、输入框、卡片、导航等都有对应组件。
- **缺点**：需改代码（控件类名与部分 API）；GPLv3，闭源/商业需处理许可。
- **适合**：愿意逐步替换控件、且能接受 GPL 或购买商业许可的项目。
- **详见**：`desktop/docs/PySide6-Fluent-Widgets-可行性评估.md`。

---

## 3. qt-material（推荐：改造成本最低）

- **包名**：`qt-material`（PyPI）
- **方式**：**仅加一行样式**，不换控件类名，现有 `QPushButton`、`QLineEdit`、`QComboBox` 等保持不变。
- **许可证**：**BSD-2-Clause**，商业友好。
- **支持**：PySide6 / PyQt6 官方支持；Python 3.7+。

### 使用方式

```python
# 在 main.py 或应用入口，创建 QApplication 之后
from qt_material import apply_stylesheet

app = QApplication(sys.argv)
apply_stylesheet(app, theme='dark_teal.xml')   # 深色 + 青绿主色
# 或 dark_blue.xml, dark_purple.xml 等
```

### 内置主题示例（深色）

- `dark_teal.xml`、`dark_blue.xml`、`dark_cyan.xml`、`dark_amber.xml`、`dark_purple.xml` 等。
- 可用 `list_themes()` 列出全部；支持自定义主色（XML 或 `extra` 字典）。

### 优点

- **改动极小**：入口一行 `apply_stylesheet`，现有界面即可统一变好看，按钮、输入框、表格、分组框等都会应用 Material 风格。
- **不碰业务逻辑**：无需把 `QPushButton` 改成别的类，图标/文字仍用现有方式即可。
- **可调**：支持主色、密度、危险/成功/警告按钮样式（如 `setProperty('class', 'danger')`），可与现有 `styles.py` 配合或逐步替代。

### 缺点

- 只是样式，没有新控件类型；若想要「完全 Fluent 导航/卡片」需自己布局，或再考虑 Fluent-Widgets。
- 深色主题下部分控件边缘/对比度可能需微调（一般可接受）。

### 依赖

- 仅 **Jinja2**（用于生成 QSS），无额外大型依赖。

---

## 4. QtModernRedux6

- **包名**：`QtModernRedux6`（PyPI），注意大小写。
- **方式**：提供**现代深色主题**的样式与（可选）**无标题栏/自定义标题栏**窗口；控件仍为标准 Qt 控件，通过样式表美化。
- **许可证**：**MIT**，商业友好。
- **支持**：Python 3.9+，PySide6 6.3.0+；在 Windows/macOS/Ubuntu 上测试过。

### 特点

- 跨平台、跨 DPI 外观一致；矢量图标替代部分 Fusion 默认图标；支持无边框窗口、阴影、自定义标题栏。
- 若只想要「整体变好看」而不改窗口形态，可仅用其样式部分；若要做「类 Chrome 标签栏」等再考虑其窗口能力。

### 缺点

- 偏**深色**风格，亮色主题支持不如 qt-material 丰富；文档较少，需参考仓库示例。
- 版本更新不如 qt-material 频繁（如 0.9.15 为 2023 年）。

### 适合

- 希望**深色、偏「现代桌面」**且**许可证宽松（MIT）**时，可作为 qt-material 的备选。

---

## 5. 其他（简要）

- **Lilac**：Qt6 的 QStyle 主题，偏 C++/QML 生态，Python/PySide6 使用资料较少，暂不优先。
- **Qt Material UI**（qt-material-ui）：Material 3 **组件库**（非纯样式），若日后考虑「换控件」可再调研；当前以「最小改动解决美观」为主时，优先 qt-material 更合适。
- **自写 QSS**：当前项目已有 `styles.py`，若只做小范围微调（如只改按钮圆角、颜色）可继续扩展；若希望**整体风格统一、少维护**，用 qt-material 或 QtModernRedux6 更省事。

---

## 6. 建议选择（针对「主要解决美观」）

| 目标 | 推荐 |
|------|------|
| **改动最少、尽快变好看** | **qt-material**：入口一行 `apply_stylesheet(app, theme='dark_teal.xml')`，BSD 许可，无 GPL 顾虑。 |
| **要 Fluent 风格 + 新组件（按钮/卡片/导航）** | **PySide6-Fluent-Widgets**：见单独可行性评估，注意 GPLv3。 |
| **要深色现代风格 + MIT 许可** | **QtModernRedux6**：样式 + 可选窗口增强，代码改动仍以「应用样式」为主。 |

**综合**：若当前首要目标是「美观、图标/文字别丑」，且希望**少改代码、无许可负担**，优先试 **qt-material**；若试用后仍希望更「Fluent/组件化」，再在部分界面引入 **PySide6-Fluent-Widgets** 做渐进替换。

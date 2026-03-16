# PySide6-Fluent-Widgets 界面改造可行性评估

## 1. 库概况

| 项目 | 说明 |
|------|------|
| **包名** | `PySide6-Fluent-Widgets`（PyPI），导入名 `qfluentwidgets` |
| **版本** | 当前 1.11.x，持续维护（2025–2026 仍有发版） |
| **绑定** | 基于 **PySide6**，与当前桌面技术栈一致 |
| **文档** | https://qfluentwidgets.com（组件、主题、示例） |
| **依赖** | PySide6、PySideSix-Frameless-Window (≥0.8.0)、darkdetect |

## 2. 与本项目技术栈的匹配度

- **可行性：高**
  - 桌面端已全面使用 PySide6（`main_window`、各 Dialog、Stack/MintPy 流程、地图等），无需更换 Qt 绑定。
  - Fluent 组件与标准 Qt 控件同属 QWidget 体系，信号/槽、布局方式一致，可**逐文件、逐控件**替换，不必一次性重写。
  - 现有 `desktop/app/styles.py` 可逐步收缩，由 qfluentwidgets 的主题与组件样式接管大部分视觉效果。

## 3. 组件对应与改造范围（概念对应）

| 当前使用 | Fluent 替代 | 说明 |
|----------|-------------|------|
| QPushButton | `PushButton` / `PrimaryPushButton` / `ToolButton` | 主按钮、操作列小按钮、图标按钮 |
| QLineEdit | `LineEdit` / `SearchLineEdit` | 路径、参数输入 |
| QComboBox | `ComboBox` | 下拉选择 |
| QProgressBar | `ProgressBar` | 进度条 |
| QTableWidget | 继续用 QTableWidget，仅单元格内放 Fluent 按钮 | 步骤表可只换“操作”列按钮 |
| QGroupBox | `GroupBox` / `CardWidget` | 分组、卡片 |
| QPlainTextEdit | `PlainTextEdit` | 日志区 |
| QDialog | 保持 QDialog，内部用 Fluent 控件 | 或改用 `MessageBox` / Fluent 弹窗 |
| 主窗口 | 可选 `MSFluentWindow` + 导航 | 改动大，可后期再做 |

**结论**：  
- **最小可行**：只把“丑”的部分（如 Stack 流程的操作列、顶部打开/复制按钮）换成 Fluent 的 `PushButton`/`ToolButton`，其余布局和逻辑不变。  
- **中等范围**：所有 Dialog（定义工作区、Stack 配置、S1 导入、MintPy 配置等）的表单控件改为 Fluent（LineEdit、ComboBox、PushButton 等）。  
- **完整改造**：主窗口改为 Fluent 导航 + 各页用 Card/GroupBox + 全局主题（亮/暗/主题色），工作量最大。

## 4. 风险与约束

| 项 | 说明 |
|----|------|
| **许可证** | 库为 **GPLv3**。若项目闭源或商业分发，需遵守 GPL 或购买作者提供的[商业许可](https://qfluentwidgets.com/price)。 |
| **Frameless 依赖** | 依赖 `PySideSix-Frameless-Window`，若仅用普通控件、不启用无边框/亚克力窗口，一般不影响现有窗口形态；若将来用 Fluent 主窗口样式，会涉及标题栏与窗口效果。 |
| **PySide6 版本** | 官方约束未写死 PySide6 小版本，建议在 6.6+ 上验证（与当前 requirements 一致）。 |
| **自定义控件** | 地图（`tile_map_widget`）、产品查看（`product_viewer`）等可继续用现有实现，仅外层容器或相邻按钮用 Fluent，无需重写核心逻辑。 |

## 5. 实施建议（分阶段）

1. **POC（1–2 天）**  
   - 在 `desktop/requirements.txt` 增加：`PySide6-Fluent-Widgets`。  
   - 仅改 **Stack 流程** 中“操作”列 5 个按钮为 `qfluentwidgets.PushButton` 或 `ToolButton`（可配合 `FluentIcon`），顶部“打开目录”“复制路径”一并替换。  
   - 不改主窗口、不改其它对话框，确认无报错、样式与分辨率下显示正常。

2. **按界面渐进替换（1–2 周）**  
   - 按使用频率改：Stack 配置对话框 → 定义工作区 → S1 导入 → MintPy 配置 → 其它 Dialog。  
   - 每步只替换控件类型与必要属性（如 placeholder、tooltip），逻辑与信号槽保持不变。  
   - 在 `main.py` 或入口处调用 `setTheme(Theme.DARK)` / `setThemeColor()`，与现有深色风格统一。

3. **（可选）主窗口与全局风格**  
   - 若希望整体为 Fluent 导航 + 多页布局，再考虑将 `QMainWindow` 换为 `MSFluentWindow` 并迁移侧边栏/内容区；可与产品/需求一起评估是否必要。

## 6. 结论与推荐

- **可行性**：**可行**。PySide6-Fluent-Widgets 与当前 PySide6 技术栈兼容，支持渐进式替换，无需一次性重写。  
- **推荐路径**：  
  - 先做 **POC**：仅 Stack 流程页的操作按钮 + 顶部两个按钮改为 Fluent，验证依赖与观感。  
  - 再按“先按钮与表单，后主窗口”的顺序逐步替换，既改善“文字/图标丑”的问题，又控制风险和工期。  
- **前提**：确认项目对 GPLv3 或商业许可无异议后再全面采用。

---

*评估基于 PySide6-Fluent-Widgets 1.11.x 与当前桌面代码结构（2025）。*

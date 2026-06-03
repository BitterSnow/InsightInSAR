# Insight InSAR 操作说明书

本目录存放操作说明书源文件、PDF 输出和后续需要补充的截图。

## 当前文件

| 文件 | 说明 |
|------|------|
| `operation-manual-placeholder.html` | 说明书源文件，内含截图占位框 |
| `Insight_InSAR_Operation_Manual_Placeholder.pdf` | PDF 占位版，推荐先查看这一份 |
| `Insight_InSAR_操作说明书_截图占位版.pdf` | 中文文件名副本 |
| `screenshots/` | 后续补充截图的位置 |

## 截图补充方式

PDF 最后一章包含完整截图清单。建议按编号命名截图，例如：

```text
manual/screenshots/S-05-main-window.png
manual/screenshots/S-10-dem-dialog.png
manual/screenshots/S-17-mintpy-flow.png
```

补齐截图后，可以把截图发给我或直接放入 `screenshots/` 目录。我会把 HTML 中的占位框替换为真实图片，并重新导出完整版 PDF。

## 重新导出 PDF

如果只是修改文字或版式，可用 Chrome headless 重新导出：

```powershell
cd D:\coding\insar-system
$html = (Resolve-Path manual\operation-manual-placeholder.html).Path.Replace('\','/')
$pdf = (Join-Path (Resolve-Path manual).Path 'Insight_InSAR_Operation_Manual_Placeholder.pdf')
& 'C:\Program Files\Google\Chrome\Application\chrome.exe' --headless=new --disable-gpu --no-pdf-header-footer --print-to-pdf="$pdf" "file:///$html"
```

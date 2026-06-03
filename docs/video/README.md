# Insight InSAR 教学视频素材（Cursor + TTS）

本目录存放 **解说词、分镜、检查清单** 与 **TTS 音频**，不存放成片 MP4。

## 在 Cursor 里生成文案

在对话中说明需求，并引用技能，例如：

```text
使用 insar-tutorial-video 技能，根据最新文档生成完整教学视频解说词和分镜清单。
```

或：`@insar-tutorial-video` 刷新 `narration-full.md`

Agent 会读取 `README.md`、`packaging/README.md` 等，并写入本目录。

## 文件说明

| 文件 | 用途 |
|------|------|
| `narration-full.md` | 完整配音稿（粘贴到任意 TTS 或下面脚本） |
| `narration-part*.md` | 分段配音（可选） |
| `shot-list.md` | 录屏分镜 |
| `recording-checklist.md` | 开录前检查 |
| `manifest.json` | 最近一次生成记录与音频路径 |
| `audio/*.mp3` | `tts_batch.py` 输出（见下方已生成列表） |

### 当前已生成音频

| 目录 | 音色 | 说明 |
|------|------|------|
| `audio-optimized/` | 云希 `zh-CN-YunxiNeural`（男） | 新版实操干货稿：全文 + 分章 + 三段，推荐使用 |
| `audio/` | 晓晓 `zh-CN-XiaoxiaoNeural`（女） | 全文 + 分段 + 三幕 |
| `audio-male/` | 云希 `zh-CN-YunxiNeural`（男） | 同上结构，推荐教学片头 |

新版男声全文：`audio-optimized/narration-full.mp3`。分章剪辑用 `full-01-` 到 `full-06-` 文件；三段剪辑用 `part1-` / `part2-` / `part3-` 前缀文件。

## 批量生成配音（Edge TTS）

```powershell
cd D:\coding\insar-system
pip install -r scripts/video/requirements-video.txt
python scripts/video/tts_batch.py docs/video/narration-full.md -o docs/video/audio-optimized --voice zh-CN-YunxiNeural
```

可选参数：

```powershell
python scripts/video/tts_batch.py docs/video/narration-full.md --voice zh-CN-XiaoxiaoNeural --rate +0%
python scripts/video/tts_batch.py docs/video/narration-full.md --split-by-heading --prefix full- -o docs/video/audio-optimized --voice zh-CN-YunxiNeural
python scripts/video/tts_batch.py docs/video/narration-part2-install.md -o docs/video/audio
```

列出常用中文音色：

```powershell
python scripts/video/tts_batch.py --list-voices
```

## 人工后续步骤（Cursor 外）

1. 按 `shot-list.md` 用 OBS 等录屏  
2. 用剪映 / CapCut / Premiere 对齐 `audio-optimized/` 与画面  
3. 字幕可用剪映识别或 Whisper，再与 `narration-full.md` 校对  

## 忽略大文件（可选）

若不想提交 mp3，在 `.gitignore` 增加：

```gitignore
docs/video/audio/
```

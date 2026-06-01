# 录制前检查清单

## 环境

- [ ] Windows 10/11，WSL2 已启用（`wsl -l -v` 正常）
- [ ] 演示用安装根目录已包含：
  - [ ] `InSAR Desktop/`
  - [ ] `InSAR WSL Deploy Wizard/`
  - [ ] `insar-wsl.tar`
- [ ] 已成功跑过一次部署向导（或准备干净 VM 从头录安装段）

## 录屏设置

- [ ] 分辨率 1920×1080，帧率 30
- [ ] 关闭系统通知、屏保
- [ ] 鼠标指针可见、移动不要太快
- [ ] 窗口标题栏可见（便于观众辨认向导 vs Desktop）

## 音频

- [ ] 已生成 `docs/video/audio/*.mp3`（`python scripts/video/tts_batch.py docs/video/narration-full.md`）
- [ ] 试听无乱码、无过长停顿
- [ ] 口播与 TTS 二选一，避免双音轨

## 素材备份

- [ ] 保留原始录屏 MP4/MKV
- [ ] 保留 `narration-full.md` 与成片项目文件

## 排错对照（剪辑时字幕可用）

| 现象 | 优先检查 |
|------|----------|
| 界面能开、任务失败 | 是否先运行部署向导；`wsl_config.env` 是否存在 |
| 向导报错 | WSL2 是否启用 |
| 无 WSL 处理 | `insar-wsl.tar` 是否在同次安装包中 |

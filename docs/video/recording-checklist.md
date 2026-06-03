# 录制前检查清单

## 安装演示

- [ ] Windows 10/11，WSL2 已启用，`wsl -l -v` 正常
- [ ] 演示安装根目录包含三件套：
  - [ ] `InSAR Desktop/`
  - [ ] `InSAR WSL Deploy Wizard/`
  - [ ] `insar-wsl.tar`
- [ ] 如果录“从零部署”，准备一个未导入过该发行版的干净环境
- [ ] 如果录“已部署环境”，提前确认 `wsl_config.env` 已存在且主程序能读取

## 示例数据

- [ ] Sentinel-1 SLC zip 或 `.SAFE` 数据目录可访问
- [ ] Orbit 目录已准备好
- [ ] Aux 目录已准备好
- [ ] DEM 原始瓦片目录或现成 DEM 文件已准备好
- [ ] 有一个小范围工作区，最好可用 KML 或明确 SNWE 数值快速复现
- [ ] 已用小样本至少跑通过一次：DEM、S1 导入、Stack 初始化、MintPy 初始化

## 录屏设置

- [ ] 分辨率 1920×1080，帧率 30
- [ ] 关闭通知、聊天软件弹窗和屏保
- [ ] 鼠标指针可见，点击前停顿半秒
- [ ] 窗口标题栏可见，方便观众区分向导、Desktop、PowerShell
- [ ] 文件路径中如含敏感信息，录制前改成演示路径

## 音频

- [ ] 已生成新版音频：`docs/video/audio-optimized/`
- [ ] 试听 `narration-full.mp3`，确认无乱码、无异常停顿
- [ ] 如果分段剪辑，使用 `part1-`、`part2-`、`part3-` 或 `full-xx-` 文件

## 剪辑时保留的排错画面

| 现象 | 画面或字幕提示 |
|------|----------------|
| 主界面能打开但任务失败 | 先查是否运行部署向导，是否存在 `wsl_config.env` |
| WSL 检查失败 | 先查 WSL2 是否启用，`wsl -l -v` 是否正常 |
| S1 导入失败 | 查 SAFE、Orbit、DEM、Aux 路径是否能被 WSL 访问 |
| Stack 找不到数据 | 查 SLC zip 原始路径和 WSL 盘符挂载 |
| MintPy load_data 失败 | 查 Stack 输出目录是否包含 reference、baselines、merged/interferograms、merged/geom_reference |

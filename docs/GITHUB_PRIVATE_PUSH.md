# 将 insar-system 推送到 GitHub 私有仓库

## 当前状态

- 已在项目根目录执行 `git init`，仓库已初始化。
- `.gitignore` 已补充 Python/InSAR 常见忽略项（`.venv`、`__pycache__` 等）。
- 因之前 `git add -A` 在后台运行，可能留下 `.git/index.lock`，需要先处理锁再继续。

---

## 第一步：解除 Git 锁（若存在）

若执行 `git status` 或 `git add` 时提示 “Another git process seems to be running”：

1. 关闭所有 Cursor 终端里正在运行的 git 命令。
2. 在资源管理器中确认没有其他程序在使用 `d:\coding\insar-system` 下的文件。
3. 删除锁文件（在 PowerShell 中执行）：
   ```powershell
   Remove-Item "d:\coding\insar-system\.git\index.lock" -Force -ErrorAction SilentlyContinue
   ```

---

## 第二步：本地首次提交

在项目根目录执行（PowerShell 或 Cursor 终端）：

```powershell
cd d:\coding\insar-system

# 暂存所有文件（若 lib/ 或 data/ 很大，首次 add 可能较慢）
git add -A

# 创建首次提交，默认分支为 master
git commit -m "Initial commit: InSAR system (backend, desktop, ISCE2/MintPy integration)"

# 将默认分支改名为 main（与 GitHub 推荐一致）
git branch -m main
```

若希望**不把大目录推上去**，可先不 add 它们，并在 `.gitignore` 中忽略后再提交，例如：

```powershell
# 仅提交主要代码与配置（不包含 lib、data 等）
git add .gitignore .env.example CLAUDE.md README.md backend desktop docs scripts docker-compose.yml shared_models.py config mcp.json
git add .cursor .vscode
# 按需添加其他文件/目录
git commit -m "Initial commit: InSAR system (core code and config)"
git branch -m main
```

---

## 第三步：在 GitHub 上创建私有仓库

1. 打开：<https://github.com/new>  
2. **Repository name**：例如 `insar-system`（或你喜欢的名字）。  
3. **Description**：可选，如 “B/S InSAR processing system (FastAPI, PySide6, ISCE2/MintPy)”.  
4. 选择 **Private**。  
5. **不要**勾选 “Add a README file” / “Add .gitignore” / “Choose a license”（本地已有）。  
6. 点击 **Create repository**。

---

## 第四步：添加远程并推送

创建好空仓库后，GitHub 会给出仓库 URL，例如：

- HTTPS: `https://github.com/你的用户名/insar-system.git`
- SSH: `git@github.com:你的用户名/insar-system.git`

在本地执行（把 `你的用户名/insar-system` 换成你的实际地址）：

```powershell
cd d:\coding\insar-system

# 添加远程（HTTPS 示例）
git remote add origin https://github.com/你的用户名/insar-system.git

# 推送到 GitHub，并设置上游分支为 main
git push -u origin main
```

若用 SSH：

```powershell
git remote add origin git@github.com:你的用户名/insar-system.git
git push -u origin main
```

首次推送若用 HTTPS，会提示在浏览器登录 GitHub 或输入凭据；若用 SSH，需已在 GitHub 添加 SSH 公钥。

---

## 可选：之后不再跟踪大目录

若首次提交里包含了 `lib/` 或 `data/` 且想从仓库中移除（保留本地文件）：

```powershell
# 从 Git 中移除，但保留本地文件
git rm -r --cached lib/
# 或
git rm -r --cached data/

# 在 .gitignore 中确保有 lib/ 或 data/
# 然后提交
git add .gitignore
git commit -m "Stop tracking lib/ (or data/)"
git push
```

---

## 小结

| 步骤 | 操作 |
|------|------|
| 1 | 若有锁，删除 `.git/index.lock` |
| 2 | `git add -A` → `git commit -m "Initial commit: ..."` → `git branch -m main` |
| 3 | 在 GitHub 新建 **Private** 空仓库 |
| 4 | `git remote add origin <你的仓库URL>` → `git push -u origin main` |

完成后，代码即在你的 GitHub 私有仓库中，仅你自己（及你邀请的协作者）可见。

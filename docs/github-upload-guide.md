# 上传到 GitHub 指南

这份指南适用于把当前项目上传到一个新的 GitHub 仓库，或把本地提交推送到已有仓库。

## 1. 上传前检查

在项目根目录执行：

```powershell
git status
```

确认这些内容不应被提交：

- `.env`、`.env.*` 里的密钥和本地配置
- `tools/python/`、`tools/node/` 便携运行时
- `frontend/node_modules/`
- `frontend/dist/`
- 日志、缓存、临时文件

本仓库的 `.gitignore` 已覆盖这些常见目录。项目报告、PPT、PDF 和文档如果是交付物，可以正常提交；单个文件不要超过 GitHub 的 100 MB 限制。

## 2. 在 GitHub 创建仓库

1. 打开 GitHub，点击 New repository。
2. 填写仓库名，例如 `ai-debate-arena`。
3. 不要勾选自动生成 README、`.gitignore` 或 License，避免和本地仓库冲突。
4. 创建后复制仓库地址，可以是 HTTPS 或 SSH。

## 3. 绑定远程仓库

新仓库第一次绑定：

```powershell
git remote add origin https://github.com/<你的用户名>/<仓库名>.git
git branch -M main
git push -u origin main
```

如果已经绑定过远程仓库：

```powershell
git remote -v
git push
```

如果远程地址需要修改：

```powershell
git remote set-url origin https://github.com/<你的用户名>/<仓库名>.git
git push -u origin main
```

## 4. 常见问题

如果 GitHub 提示文件太大，先查看大文件：

```powershell
git ls-files | ForEach-Object { Get-Item $_ -ErrorAction SilentlyContinue } | Sort-Object Length -Descending | Select-Object -First 20 FullName,Length
```

如果误把密钥加入暂存区，先取消暂存，不要提交：

```powershell
git restore --staged .env
```

如果远程仓库已经有提交，先拉取并处理差异：

```powershell
git pull --rebase origin main
git push
```

## 5. 推荐上传前验证

```powershell
tools\python\python.exe -m pytest backend\tests\test_rag_and_export.py -q
cd frontend
npm.cmd test
npm.cmd run build
```

验证通过后再推送，GitHub 上的 README、报告导出说明和项目结构会更清楚。

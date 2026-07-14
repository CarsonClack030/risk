# Risk Studio

新的桌面版项目，采用 `Tauri + React` 作为界面层，`Python` 作为本地 sidecar 计算服务，并把 SQLite 模板库内嵌到后端资源里。

## 目录

- `src/`: React 前端工作台
- `src-tauri/`: Tauri 桌面壳与 sidecar 启动逻辑
- `backend/`: Python API、计算服务、嵌入数据库与 sidecar 构建脚本

## 本地开发

1. 安装 Node.js、Rust 和 Tauri CLI。

推荐使用 `rustup` 安装 Rust：

```bash
curl https://sh.rustup.rs -sSf | sh -s -- -y --profile minimal
export PATH="$HOME/.cargo/bin:$PATH"
rustup default stable
```
2. 安装前端依赖：

```bash
npm install
```

3. 可选：单独启动后端调试。

```bash
python3 backend/main.py --host 127.0.0.1 --port 38911
```

4. 启动桌面开发环境。

```bash
npm run dev
```

桌面壳现在会优先尝试 `127.0.0.1:38911`，如果该端口已被旧实例或其它程序占用，会自动切换到一个空闲本地端口，因此不会再因为端口冲突直接启动失败。

如果本机没有把 Python 暴露为 `python3`，可以先设置：

```bash
export RISK_PYTHON_BIN=/你的/python
```

## 版本与检查更新

界面顶部会显示当前软件版本，并提供“检查更新”按钮。用户主动检查时，软件会读取
`wangminglei030/risk` 仓库的最新正式 GitHub Release：

- 当前版本已经是最新版本时，只显示状态提示。
- 发现更高版本时，先弹窗询问用户，不会自动下载或静默安装。
- 用户确认后，使用系统默认浏览器打开 GitHub Release 页面，自行选择 Windows 或 macOS 安装包。

发布新版本时，要保持下面三个文件中的版本号一致：

```text
package.json
src-tauri/Cargo.toml
src-tauri/tauri.conf.json
```

推送 `v1.1.0` 这类版本 tag 后，`.github/workflows/release.yml` 会自动验证源码、构建
macOS DMG 与 Windows NSIS 安装包，并在两个平台都成功后创建正式 Release。草稿
Release 不会被“最新正式版本”接口识别。

注意：GitHub 私有仓库不会向未登录的桌面客户端公开 Release 信息，而且不能把 Personal
Access Token 写进软件安装包。面向其他用户分发更新前，需要把仓库或专用下载仓库设为公开。

## 生成 sidecar

后端 sidecar 打包脚本会把 `template.db` 一起打入单文件可执行程序：

```bash
python3 -m pip install -r backend/requirements-build.txt
python3 backend/build_sidecar.py
```

当前工作区文件导入支持：

- `.xlsx`
- `.xls`
- `.csv`
- `.txt`

桌面版导入时会打开系统文件选择窗口；保存导入模板和导出计算结果时会打开系统“另存为”窗口，
文件路径和文件名均由用户自行决定。

生成物默认位于 `backend/bin/`，文件名会自动带上目标三元组，例如：

```text
backend/bin/risk-backend-aarch64-apple-darwin
```

推荐的一键发布命令：

```bash
./build_release.sh
./build_release.sh dmg
```

当前已经验证通过的桌面编译检查命令：

```bash
export PATH="$HOME/.cargo/bin:$PATH"
npm run tauri -- build --debug --no-bundle
```

当前已经验证通过的 macOS `.app` 打包命令：

```bash
export PATH="$HOME/.cargo/bin:$PATH"
npm run tauri -- build --debug -b app --no-sign
```

也可以直接使用这些脚本：

```bash
npm run build:sidecar
npm run build:debug:app
npm run build:release:app
npm run build:release:dmg
```

随后再执行 `npm run build`，Tauri 会按 `src-tauri/tauri.conf.json` 里的 `externalBin` 约定把 sidecar 一起打包。

## Windows EXE

当前这台 macOS 机器不能直接产出可运行的 Windows `.exe`，因为缺少 Windows 构建环境和对应的 Python sidecar 打包链路。项目里已经补好了 Windows 打包命令和脚本，拿到 Windows 机器后可以直接执行：

```powershell
cd risk_tauri
.\build_release_windows.ps1
```

或者分步执行：

```powershell
python -m pip install -r backend/requirements-build.txt
python backend/build_sidecar.py
npm ci
npm run build:release:windows
```

成功后重点看这两个目录：

```text
src-tauri/target/release/bundle/nsis
src-tauri/target/release
```

其中 `nsis` 目录里会有 Windows 安装包 `.exe`。如果你把这个项目放到 GitHub 仓库里，也可以直接用 [windows-build.yml](/Users/carson/Documents/risk/risk_tauri/.github/workflows/windows-build.yml) 在 `windows-latest` 上自动产出可下载的构建产物。

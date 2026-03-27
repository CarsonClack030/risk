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

## 生成 sidecar

后端 sidecar 打包脚本会把 `template.db` 一起打入单文件可执行程序：

```bash
python3 -m pip install -r backend/requirements-build.txt
python3 backend/build_sidecar.py
```

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

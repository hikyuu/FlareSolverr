# FlareSolverr 发布流水线（miao fork）

本目录是上游 FlareSolverr 3.5.2 的 Actions 配置，**已按 miao 的需要收敛**：
只保留「Windows onedir 压缩包」这一条发布链路，Docker 镜像流水线保留文件但默认关闭。

改动处均带 `miao fork patch` 注释，便于日后与上游 rebase。

## 流水线一览

| 文件 | 触发 | 产物 | 状态 |
| --- | --- | --- | --- |
| `release.yml` | push 到 `miao`（或手动 dispatch） | 打 `v*.*.*` tag + release + `flaresolverr_windows_x64.zip` | 启用 |
| `autotag.yml` | 仅 `workflow_dispatch` | 上游的两段式打 tag | **已停用**（见下） |
| `release-docker.yml` | 仅 `workflow_dispatch`（手动） | 多架构 Docker 镜像（DockerHub / ghcr.io） | **禁用自动触发** |

## 发布链路

```
push 到 miao
  └─ release.yml（单次运行，两步 job）
       ├─ meta            （ubuntu-22.04）
       │    ├─ 读 package.json 的 version
       │    ├─ gh release view 已存在 → skip（不 bump 就不发版）
       │    ├─ 按「上一个 tag..HEAD」生成 changelog（--sort=v:refname）
       │    └─ 建 tag vX.Y.Z + release
       └─ build-package   （windows-latest，needs: meta，skip 时整段跳过）
            ├─ pip install -r requirements.txt
            ├─ pip install pyinstaller==6.22.2
            ├─ cd src && python build_package.py
            │    ├─ download_chromium()   下 Chromium snapshot
            │    ├─ run_pyinstaller()     --onedir（显式）
            │    └─ compress_package()    dist/flaresolverr_windows_x64.zip
            └─ gh release upload vX.Y.Z ./dist/flaresolverr_windows_x64.zip --clobber
```

### 为什么不是上游的两段式

上游 `autotag.yml` 打 tag → tag push 触发 `release.yml`。这条链**只在用 PAT 时成立**：
用内置 `GITHUB_TOKEN` 打出的 tag 属于「token 产生的事件」，GitHub 不会为它新建
workflow run（防递归规则，`workflow_dispatch` / `repository_dispatch` 除外）。

fork 不想维护 PAT，所以把打 tag 与出包合并进 `release.yml` 的同一次运行——同一次
运行内的 job 之间用 `needs` 串联，不经过事件系统，因此不受该规则影响。

恢复两段式（需要 PAT）：

1. `autotag.yml` 的 `on:` 改回 `push: branches: ["miao"]`
2. `release.yml` 的 `on:` 改回 `push: tags: ["v*.*.*"]`
3. 两个 workflow 的 `secrets.GITHUB_TOKEN` 换成同一个 PAT secret（如 `RELEASE_PAT`）


`flaresolverr_windows_x64.zip` 解压后是 **onedir 目录**：

```
flaresolverr/
├── flaresolverr.exe      # 入口
├── _internal/            # 依赖 + 内嵌的 Chromium
└── ...
```

> `--onedir` 在 `src/build_package.py` 里是**显式参数**。PyInstaller 6.x 的默认值
> 本来就是 onedir，写死是为了防止上游改默认值后产物在「单文件 / 目录」之间静默漂移。

## fork 自建发布所需的配置

**不需要任何自定义 secret**。`secrets.GH_PAT` 已换成内置 `secrets.GITHUB_TOKEN`，
启用中的 `release.yml` 声明了 `permissions: contents: write`（建 tag / release、上传资产都需要）。

| 项 | 值 | 说明 |
| --- | --- | --- |
| Secret | 无 | 用仓库自动注入的 `GITHUB_TOKEN` |
| 权限 | `contents: write` | 已在 workflow 内声明，无需改仓库设置 |
| 发布分支 | `miao` | `release.yml` 的 push 过滤写的是 `miao`；fork 若用别的名字要同步改 |
| 上游分支 | `master` | 只跟随 `upstream/master`，推它不会触发发版 |
| Release 归属 | 当前仓库 | `softprops/action-gh-release` 默认作用域就是运行时仓库，无需改仓库名 |

发布流程：把 `package.json` 的 `version` 改成目标版本并推 `miao`，`release.yml` 在
同一次运行里打 tag、建 release、出 Windows 包。**版本号没变就不会发版**（`meta` job
的 `gh release view` 命中即 skip），所以每次要发布都必须 bump。

## 恢复 Docker 流水线

`release-docker.yml` 的 `on:` 现在是：

```yaml
on: workflow_dispatch:
```

改回上游写法即可恢复自动发布：

```yaml
on:
  push:
    tags:
      - "v*.*.*"
  pull_request:
    branches:
      - master
```

恢复前需要补三个 secret，否则登录步骤会失败：

| secret | 用途 |
| --- | --- |
| `DOCKERHUB_USERNAME` | DockerHub 登录 |
| `DOCKERHUB_TOKEN` | DockerHub 登录 |
| `GITHUB_TOKEN` | 推 `ghcr.io`，需要 `packages: write` 权限 |

## 已知取舍

- **只出 Windows 包**：上游矩阵里的 `ubuntu-22.04` 已移除，因此不再产出
  `flaresolverr_linux_x64.tar.gz`。若将来需要 Linux 自建包，把矩阵加回来即可。
- **Docker 流水线是死文件**：不会自动跑，需要手动 dispatch。这是刻意的，
  目的是保留恢复能力但不给 fork 增加额外失败点。
- **产物仍含 Chromium**：Win/Linux 的 zip 都把 Chromium 打进包里（`build_package.py`
  的 `--add-data dist_chrome/chrome`），体积数百 MB，且内含 GPL-3.0 的
  `undetected_chromedriver`。**打包时不得裁剪 `LICENSE`**，对外分发需保留许可与声明。

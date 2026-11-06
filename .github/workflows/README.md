# FlareSolverr 发布流水线（miao fork）

本目录是上游 FlareSolverr 3.5.2 的 Actions 配置，**已按 miao 的需要收敛**：
只保留「Windows onedir 压缩包」这一条发布链路，Docker 镜像流水线保留文件但默认关闭。

改动处均带 `miao fork patch` 注释，便于日后与上游 rebase。

## 流水线一览

| 文件 | 触发 | 产物 | 状态 |
| --- | --- | --- | --- |
| `autotag.yml` | push 到 `miao` | 按 `package.json` 的 `version` 打 `v*.*.*` tag | 启用 |
| `release.yml` | push `v*.*.*` tag | release + `flaresolverr_windows_x64.zip` | 启用 |
| `release-docker.yml` | 仅 `workflow_dispatch`（手动） | 多架构 Docker 镜像（DockerHub / ghcr.io） | **禁用自动触发** |

## 发布链路

```
push 到 miao
  └─ autotag.yml        读 package.json version → 打 tag vX.Y.Z
       └─ release.yml   tag 触发
            ├─ create-release   （ubuntu-22.04）按上一个 tag..HEAD 生成 changelog
            └─ build-package    （windows-latest）
                 ├─ pip install -r requirements.txt
                 ├─ pip install pyinstaller==6.22.2
                 ├─ cd src && python build_package.py
                 │    ├─ download_chromium()   下 Chromium snapshot
                 │    ├─ run_pyinstaller()     --onedir（显式）
                 │    └─ compress_package()    dist/flaresolverr_windows_x64.zip
                 └─ 上传 ./dist/flaresolverr_* 到 release
```

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

**不需要任何自定义 secret**。三处 `secrets.GH_PAT` 已换成内置 `secrets.GITHUB_TOKEN`，
两个启用的工作流都加了 `permissions: contents: write`（创建 release、上传资产、打 tag 都需要）。

| 项 | 值 | 说明 |
| --- | --- | --- |
| Secret | 无 | 用仓库自动注入的 `GITHUB_TOKEN` |
| 权限 | `contents: write` | 已在 workflow 内声明，无需改仓库设置 |
| 发布分支 | `miao` | `autotag.yml` 的分支过滤写的是 `miao`；fork 若用别的名字要同步改 |
| 上游分支 | `master` | 只跟随 `upstream/master`，推它不会触发发版 |
| Release 归属 | 当前仓库 | `softprops/action-gh-release` 默认作用域就是运行时仓库，无需改仓库名 |

发布流程：把 `package.json` 的 `version` 改成目标版本并推 `miao`（或把改动合入
`miao`），`autotag.yml` 会打 tag，随后 `release.yml` 自动出包。

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

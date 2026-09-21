# CNB ⇄ GitHub 双向同步配置指南

本仓库实现 **CNB 与 GitHub 双向代码同步**，并在任一平台打 `release-v*` 标签时自动创建 Release、构建并推送 Docker 镜像。

> **拷贝到其他仓库使用时，请注意代码注释中标注 `【需修改】` 的位置，逐项替换为你的实际信息。**

---
本仓库实现 **CNB 与 GitHub 双向代码同步**，并在任一平台打 `release-v*` 标签时自动创建 Release、构建并推送 Docker 镜像。

> **拷贝到其他仓库使用时，请注意代码注释中标注 `【需修改】` 的位置，逐项替换为你的实际信息。**

---

## 📐 架构概览

| 触发端 | 事件 | 执行动作 |
|--------|------|----------|
| 触发端 | 事件 | 执行动作 |
|--------|------|----------|
| **GitHub** | 推送 `main` 分支 | 同步 `main` 到 CNB |
| **GitHub** | 推送 `release-v*` 标签 | 同步标签到 CNB → CNB 创建 Release + 构建 Docker 镜像 + 同步回 GitHub |
| **GitHub** | 推送 `release-v*` 标签 | 同步标签到 CNB → CNB 创建 Release + 构建 Docker 镜像 + 同步回 GitHub |
| **CNB** | 推送 `main` 分支 | 同步 `main` 到 GitHub（含防冲突机制） |
| **CNB** | 推送 `release-v*` 标签 | 创建 CNB Release → 同步标签到 GitHub → 构建 Docker 镜像 |
| **CNB** | 推送 `release-v*` 标签 | 创建 CNB Release → 同步标签到 GitHub → 构建 Docker 镜像 |

**防循环机制**：若 Git 推送时 ref 未变化，Git 视为 no-op，不会触发对端 Webhook。请勿在任一端自动重写提交历史（如 amend），否则会破坏该机制。
**防循环机制**：若 Git 推送时 ref 未变化，Git 视为 no-op，不会触发对端 Webhook。请勿在任一端自动重写提交历史（如 amend），否则会破坏该机制。

---

## 🛠️ 前置准备

### 1. GitHub 端
## 🛠️ 前置准备

### 1. GitHub 端

**① 创建 Personal Access Token (PAT)**
**① 创建 Personal Access Token (PAT)**

进入 GitHub → **Settings** → **Developer settings** → **Personal access tokens** → **Fine-grained tokens**，生成 Token 并配置权限：
进入 GitHub → **Settings** → **Developer settings** → **Personal access tokens** → **Fine-grained tokens**，生成 Token 并配置权限：

| 权限 | 级别 | 用途 |
|------|------|------|
| **Contents** | Read and write | 推送代码、标签 |
| **Workflows** | Read and write | **必须**，允许推送 `.github/workflows/` 文件 |
| **Metadata** | Read-only | 自动勾选，必须 |

> ⚠️ `Actions` 权限不足以推送 workflow 文件，必须显式授予 **`Workflows: Read and write`**。
> ⚠️ `Actions` 权限不足以推送 workflow 文件，必须显式授予 **`Workflows: Read and write`**。

**② 配置 GitHub Actions Secret**

进入 GitHub 仓库 → **Settings** → **Secrets and variables** → **Actions**，添加：

**② 配置 GitHub Actions Secret**

进入 GitHub 仓库 → **Settings** → **Secrets and variables** → **Actions**，添加：

- `GIT_PASSWORD`：CNB 的访问令牌（具备仓库写权限）。

### 2. CNB 端

**① 创建密钥仓库**
### 2. CNB 端

**① 创建密钥仓库**

在 CNB 创建一个**密钥仓库**（仓库类型选择「密钥仓库」），添加文件 `sync-repo-env.yml`：

```yaml
# 限制只有指定仓库可以引用此密钥文件
allow_slugs:
  - 1983shake/sync-repo                 # 【需修改】改为你的 CNB 仓库路径
  - 1983shake/sync-repo                 # 【需修改】改为你的 CNB 仓库路径

GITHUB_TOKEN: github_pat_xxxxxxxxxxxx   # 【需修改】填入 GitHub PAT
GITHUB_REPO: 1983shake/sync-repo        # 【需修改】填入 GitHub 仓库路径
GITHUB_TOKEN: github_pat_xxxxxxxxxxxx   # 【需修改】填入 GitHub PAT
GITHUB_REPO: 1983shake/sync-repo        # 【需修改】填入 GitHub 仓库路径
```

**② 开启 CNB 自动触发**
**② 开启 CNB 自动触发**

进入 CNB 仓库 → **设置** → **云原生构建**，勾选：
进入 CNB 仓库 → **设置** → **云原生构建**，勾选：
- ✅ 允许自动触发
- ✅ Fork 仓库默认允许自动触发（若为 Fork 仓库）

---

## 📄 配置文件模板
## 📄 配置文件模板

### 1. CNB 端 `.cnb.yml`

> 放置在 **`main` 分支的根目录**。若默认分支为 `master`，请将下文所有 `"main"` 改为 `"master"`，并同步修改 GitHub 工作流中的分支监听。
> 放置在 **`main` 分支的根目录**。若默认分支为 `master`，请将下文所有 `"main"` 改为 `"master"`，并同步修改 GitHub 工作流中的分支监听。

```yaml
# ============================================================================
# CNB 流水线配置
#   功能：
#     1. main 分支 push/commit.add -> 同步到 GitHub main
#     2. release-v* tag -> 建 CNB Release + 同步 tag 到 GitHub + 构建 Docker 镜像
#
#   拷贝到其他仓库时，请重点修改标注【需修改】的部分。
#
#   拷贝到其他仓库时，请重点修改标注【需修改】的部分。
# ============================================================================

"main":
  # 双事件保险：同时配置 push 和 commit.add，避免因事件类型不匹配导致不触发
  push:
    - imports:
        # 【需修改】替换为你的密钥仓库路径（组织/仓库/分支/文件名）
        # 【需修改】替换为你的密钥仓库路径（组织/仓库/分支/文件名）
        - https://cnb.cool/1983shake/secret-repo/-/blob/main/sync-repo-env.yml
      stages:
        - name: push main to github
          script: |
            set -e
            echo "==> 触发事件: push"
            echo "==> 当前分支: ${CNB_BRANCH}"
            git remote remove github 2>/dev/null || true
            # 【需修改】若 GitHub 仓库地址不同，GITHUB_REPO 变量已在密钥仓库中定义
            # 【需修改】若 GitHub 仓库地址不同，GITHUB_REPO 变量已在密钥仓库中定义
            git remote add github \
              "https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPO}.git"


            # 1. 推送前先拉取 GitHub 最新更改，避免并发冲突
            echo "==> 拉取 GitHub 最新更改..."
            git fetch github main


            # 2. 将本地更改变基到远程最新提交之上
            git rebase github/main || {
              echo "❌ Rebase 失败，可能存在合并冲突，请手动处理。"
              exit 1
            }
            # 3. 带重试机制的推送（最多重试 3 次）
            for i in 1 2 3; do
              echo "==> 尝试推送 (第 ${i} 次)..."
              if git push github "HEAD:main" --force-with-lease; then
                echo "✅ 推送成功"
                break
              else
                echo "⚠️ 推送失败，等待 ${i}0 秒后重试..."
                sleep ${i}0
                git fetch github main
              fi
              if [ $i -eq 3 ]; then
                echo "❌ 推送失败，已达最大重试次数。"
                exit 1
              fi
            done
            echo "==> main 同步完成"


  commit.add:
    - imports:
        # 【需修改】同上，替换为你的密钥仓库路径
        # 【需修改】同上，替换为你的密钥仓库路径
        - https://cnb.cool/1983shake/secret-repo/-/blob/main/sync-repo-env.yml
      stages:
        - name: sync new commits to github
          script: |
            set -e
            echo "==> 触发事件: commit.add"
            echo "==> 当前分支: ${CNB_BRANCH}"
            echo "==> 新增提交数: ${CNB_NEW_COMMITS_COUNT}"
            git remote remove github 2>/dev/null || true
            git remote add github \
              "https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPO}.git"

            echo "==> 拉取 GitHub 最新更改..."
            git fetch github main
            git rebase github/main || {
              echo "❌ Rebase 失败，可能存在合并冲突，请手动处理。"
              exit 1
            }

            for i in 1 2 3; do
              echo "==> 尝试推送 (第 ${i} 次)..."
              if git push github "HEAD:main" --force-with-lease; then
                echo "✅ 推送成功"
                break
              else
                echo "⚠️ 推送失败，等待 ${i}0 秒后重试..."
                sleep ${i}0
                git fetch github main
              fi
              if [ $i -eq 3 ]; then
                echo "❌ 推送失败，已达最大重试次数。"
                exit 1
              fi
            done
            echo "==> main 同步完成"

"release-v*":
  tag_push:
    - services:
        - docker
      imports:
        # 【需修改】替换为你的密钥仓库路径
        # 【需修改】替换为你的密钥仓库路径
        - https://cnb.cool/1983shake/secret-repo/-/blob/main/sync-repo-env.yml
      stages:
        - name: prepare release
          script: |
            set -e
            VERSION="${CNB_BRANCH#release-v}"
            echo "版本号: ${VERSION}"
            # 【需修改】若项目名称不是 Vael-Mux，请修改下方 title 和 description
            # 【需修改】若项目名称不是 Vael-Mux，请修改下方 title 和 description
            cat > release-options.json <<EOF
            {
              "title": "Vael-Mux_V${VERSION}",
              "description": "Release Vael-Mux V${VERSION}"
            }
            EOF
            echo "生成的 Release 配置："
            cat release-options.json

        - name: create release on cnb
          type: git:release
          optionsFrom: ./release-options.json

        - name: sync tag to github
          script: |
            set -e
            echo "==> 同步 tag ${CNB_BRANCH} 到 GitHub"
            git remote remove github 2>/dev/null || true
            git remote add github \
              "https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPO}.git"
            for i in 1 2 3; do
              echo "==> 尝试推送标签 (第 ${i} 次)..."
              if git push github \
                "refs/tags/${CNB_BRANCH}:refs/tags/${CNB_BRANCH}" --force; then
                echo "✅ 标签推送成功"
                break
              else
                echo "⚠️ 标签推送失败，等待 ${i}0 秒后重试..."
                sleep ${i}0
              fi
              if [ $i -eq 3 ]; then
                echo "❌ 标签推送失败，已达最大重试次数。"
                exit 1
              fi
            done
            echo "==> tag 同步完成"

        - name: docker build and push
          script: |
            set -e
            # 镜像基础路径自动使用 CNB 仓库路径，一般无需修改
            # 镜像基础路径自动使用 CNB 仓库路径，一般无需修改
            IMAGE_BASE="${CNB_DOCKER_REGISTRY}/${CNB_REPO_SLUG_LOWERCASE}"
            VERSION="${CNB_BRANCH#release-v}"
            echo "==> 构建版本: ${VERSION}"
            docker build \
              -t "${IMAGE_BASE}:${VERSION}" \
              -t "${IMAGE_BASE}:latest" \
              .
            docker push "${IMAGE_BASE}:${VERSION}"
            docker push "${IMAGE_BASE}:latest"
            echo "==> 镜像推送完成: ${IMAGE_BASE}:${VERSION}"
```

### 2. GitHub 端 `.github/workflows/sync-cnb.yml`

> 放置在 **`main` 分支的 `.github/workflows/` 目录下**。

> 放置在 **`main` 分支的 `.github/workflows/` 目录下**。

```yaml
# ============================================================================
# GitHub Actions：同步 GitHub -> CNB
#
# 拷贝到其他仓库时，请修改标注【需修改】的部分。
#
# 拷贝到其他仓库时，请修改标注【需修改】的部分。
# ============================================================================
name: Sync to CNB and Create Release

on:
  push:
    # 【需修改】若默认分支不是 main，请改为实际分支名
    # 【需修改】若默认分支不是 main，请改为实际分支名
    branches: [main]
    # 【需修改】若标签格式不同，请调整匹配模式
    # 【需修改】若标签格式不同，请调整匹配模式
    tags: ['release-v*']
  workflow_dispatch:

permissions:
  contents: write

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

env:
  # 【需修改】替换为你的 CNB 仓库实际地址
  # 【需修改】替换为你的 CNB 仓库实际地址
  CNB_REPO: cnb.cool/1983shake/sync-repo.git

jobs:
  sync:
    runs-on: ubuntu-latest
    timeout-minutes: 10

    steps:
      - name: Checkout code
        uses: actions/checkout@v5
        with:
          fetch-depth: 0

      - name: Configure Git and CNB remote
        run: |
          git config --global user.name "GitHub Action"
          git config --global user.email "action@github.com"
          git remote remove cnb 2>/dev/null || true
          # GIT_PASSWORD 需在 GitHub 仓库 Secrets 中配置
          # GIT_PASSWORD 需在 GitHub 仓库 Secrets 中配置
          git remote add cnb \
            "https://cnb:${{ secrets.GIT_PASSWORD }}@${{ env.CNB_REPO }}"

      - name: Extract version from tag
        id: version
        if: startsWith(github.ref, 'refs/tags/release-v')
        run: |
          VERSION="${GITHUB_REF_NAME#release-v}"
          echo "VERSION=${VERSION}" >> "$GITHUB_OUTPUT"
          echo "版本号: ${VERSION}"

      - name: Push main branch to CNB
        if: github.ref == 'refs/heads/main'
        run: |
          echo "==> 同步 main 到 CNB"
          git push cnb "HEAD:main" --force
          echo "==> main 同步完成"

      - name: Push tag to CNB
        if: startsWith(github.ref, 'refs/tags/release-v')
        run: |
          echo "==> 同步 tag ${GITHUB_REF_NAME} 到 CNB"
          git push cnb \
            "refs/tags/${GITHUB_REF_NAME}:refs/tags/${GITHUB_REF_NAME}" --force
          echo "==> tag 同步完成"

      - name: Create GitHub Release
        if: startsWith(github.ref, 'refs/tags/release-v')
        uses: softprops/action-gh-release@v2
        with:
          tag_name: ${{ github.ref_name }}
          # 【需修改】若项目名称不是 Vael-Mux，请修改此处
          # 【需修改】若项目名称不是 Vael-Mux，请修改此处
          name: Vael-Mux_V${{ steps.version.outputs.VERSION }}
          generate_release_notes: true
```

---

## 🚀 部署与验证步骤

1. **替换所有 `【需修改】` 标记**  
   逐个文件搜索 `【需修改】`，根据实际情况替换仓库路径、密钥仓库地址、项目名称、分支名等。

2. **配置 GitHub Secret**  
   在 GitHub 仓库添加 `GIT_PASSWORD`，值为 CNB 访问令牌。

3. **配置 CNB 密钥仓库**  
   确保 `sync-repo-env.yml` 中的 `allow_slugs` 包含当前仓库路径，且 `GITHUB_TOKEN`、`GITHUB_REPO` 正确。

4. **统一默认分支**  
   CNB 与 GitHub 的默认分支均设置为 `main`（或统一为其他名称）。

5. **提交并推送**  
   将 `.cnb.yml` 推送到 CNB `main` 分支，将 `.github/workflows/sync-cnb.yml` 推送到 GitHub `main` 分支。

6. **验证同步**  
   - 在 GitHub 向 `main` 推送一个提交，观察 CNB 是否收到代码并触发流水线。  
   - 在 CNB 向 `main` 推送一个提交，观察 GitHub 是否收到代码并触发 Actions。  
   - 在任一平台打 `release-v*` 标签，观察两端 Release 与 Docker 镜像是否自动生成。
## 🚀 部署与验证步骤

1. **替换所有 `【需修改】` 标记**  
   逐个文件搜索 `【需修改】`，根据实际情况替换仓库路径、密钥仓库地址、项目名称、分支名等。

2. **配置 GitHub Secret**  
   在 GitHub 仓库添加 `GIT_PASSWORD`，值为 CNB 访问令牌。

3. **配置 CNB 密钥仓库**  
   确保 `sync-repo-env.yml` 中的 `allow_slugs` 包含当前仓库路径，且 `GITHUB_TOKEN`、`GITHUB_REPO` 正确。

4. **统一默认分支**  
   CNB 与 GitHub 的默认分支均设置为 `main`（或统一为其他名称）。

5. **提交并推送**  
   将 `.cnb.yml` 推送到 CNB `main` 分支，将 `.github/workflows/sync-cnb.yml` 推送到 GitHub `main` 分支。

6. **验证同步**  
   - 在 GitHub 向 `main` 推送一个提交，观察 CNB 是否收到代码并触发流水线。  
   - 在 CNB 向 `main` 推送一个提交，观察 GitHub 是否收到代码并触发 Actions。  
   - 在任一平台打 `release-v*` 标签，观察两端 Release 与 Docker 镜像是否自动生成。

---

## ❓ 常见问题排查（FAQ）

**Q1: CNB 推送代码后工作流没有触发？**  
- 确认 CNB 仓库默认分支为 `main`，且 `.cnb.yml` 已推送到该分支根目录。  
- 确认 CNB 仓库设置中「允许自动触发」已勾选。  
- 检查 commit message 是否包含 `[ci skip]` 或 `[skip ci]`。
**Q1: CNB 推送代码后工作流没有触发？**  
- 确认 CNB 仓库默认分支为 `main`，且 `.cnb.yml` 已推送到该分支根目录。  
- 确认 CNB 仓库设置中「允许自动触发」已勾选。  
- 检查 commit message 是否包含 `[ci skip]` 或 `[skip ci]`。

**Q2: 报错 `refusing to allow a Personal Access Token to create or update workflow`**  
GitHub PAT 缺少 `Workflows` 权限。进入 Token 编辑页面，在 **Repository permissions** 中将 **Workflows** 设为 **Read and write**。Fine-grained Token 保存后立即生效。
**Q2: 报错 `refusing to allow a Personal Access Token to create or update workflow`**  
GitHub PAT 缺少 `Workflows` 权限。进入 Token 编辑页面，在 **Repository permissions** 中将 **Workflows** 设为 **Read and write**。Fine-grained Token 保存后立即生效。

**Q3: 报错 `cannot lock ref ... is at ... but expected ...`**  
并发写冲突。本配置已在 CNB 端加入 `git fetch` + `git rebase` + `--force-with-lease` + 重试机制。若仍冲突，请手动处理合并冲突。
**Q3: 报错 `cannot lock ref ... is at ... but expected ...`**  
并发写冲突。本配置已在 CNB 端加入 `git fetch` + `git rebase` + `--force-with-lease` + 重试机制。若仍冲突，请手动处理合并冲突。

**Q4: GitHub 出现 “Compare & pull request” 黄色提示**  
说明 CNB 推送到了非默认分支（如 `master`）。请统一两端默认分支为 `main`，并删除多余分支。
**Q4: GitHub 出现 “Compare & pull request” 黄色提示**  
说明 CNB 推送到了非默认分支（如 `master`）。请统一两端默认分支为 `main`，并删除多余分支。

**Q5: 密钥仓库的 `allow_slugs` 如何配置？**  
在密钥仓库的 `sync-repo-env.yml` 中通过 `allow_slugs` 声明允许引用的仓库，支持精确匹配和通配符（如 `1983shake/**`）。若省略，仅密钥仓库管理员/负责人触发的流水线可引用。
**Q5: 密钥仓库的 `allow_slugs` 如何配置？**  
在密钥仓库的 `sync-repo-env.yml` 中通过 `allow_slugs` 声明允许引用的仓库，支持精确匹配和通配符（如 `1983shake/**`）。若省略，仅密钥仓库管理员/负责人触发的流水线可引用。

---

## 📋 变量与 Secrets 汇总

| 平台 | 名称 | 存放位置 | 说明 |
|------|------|----------|------|
| GitHub | `GIT_PASSWORD` | Repository Secrets | CNB 访问令牌（仓库写权限） |
| CNB | `GITHUB_TOKEN` | 密钥仓库 `sync-repo-env.yml` | GitHub PAT（`Contents` + `Workflows` 读写） |
| CNB | `GITHUB_REPO` | 密钥仓库 `sync-repo-env.yml` | GitHub 仓库路径，如 `1983shake/sync-repo` |

---

## 💡 最佳实践建议

1. **分支统一**：确保 CNB 和 GitHub 默认分支均为 `main`。  
2. **权限最小化**：GitHub PAT 仅授予必要权限（`Contents` + `Workflows` + `Metadata`）。  
3. **定期轮换 Token**：设置合理过期时间，及时更新密钥仓库中的 `GITHUB_TOKEN`。  
4. **监控流水线**：定期查看 CNB 构建历史和 GitHub Actions 运行记录。  
5. **避免自动改写历史**：不要配置自动 amend 或 rebase 后强推的钩子，否则会破坏防循环机制。
6.

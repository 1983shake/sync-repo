# CNB ⇄ GitHub 双向同步配置指南

本文档详细说明了如何配置 CNB 和 GitHub 之间的代码双向同步、Release 自动创建及 Docker 镜像自动构建的完整流程。

## 📐 架构概览

| 触发端 | 触发事件 | 执行动作 |
|--------|----------|----------|
| **GitHub** | 推送 `main` 分支 | 同步 `main` 到 CNB |
| **GitHub** | 推送 `release-v*` 标签 | 同步标签到 CNB -> CNB 创建 Release + 构建 Docker 镜像 + 同步回 GitHub |
| **CNB** | 推送 `main` 分支 | 同步 `main` 到 GitHub（含防冲突机制） |
| **CNB** | 推送 `release-v*` 标签 | 创建 CNB Release -> 同步标签到 GitHub -> 构建 Docker 镜像 |

**防循环机制**：若 Git 推送时 ref 未变化，Git 视为 no-op，不会触发对端的 Webhook。请勿在任一端自动重写提交历史（如 amend），否则会破坏该机制。

---

## 🛠️ 前置准备（Secrets & Tokens）

### 1. GitHub 端配置

**创建 Personal Access Token (PAT)**
进入 GitHub -> **Settings** -> **Developer settings** -> **Personal access tokens** -> **Fine-grained tokens**，生成 Token 并配置以下权限：

| 权限 | 级别 | 用途 |
|------|------|------|
| **Contents** | Read and write | 推送代码、标签 |
| **Workflows** | Read and write | **必须**，允许推送 `.github/workflows/` 文件 |
| **Metadata** | Read-only | 自动勾选，必须 |

> ⚠️ **注意**：`Actions` 权限不足以推送 workflow 文件，必须显式授予 **`Workflows: Read and write`**。

**配置 GitHub Actions Secret**
进入 GitHub 仓库 -> **Settings** -> **Secrets and variables** -> **Actions**，添加：
- `GIT_PASSWORD`：CNB 的访问令牌（具备仓库写权限）。

### 2. CNB 端配置

**创建密钥仓库**
在 CNB 创建一个**密钥仓库**（仓库类型选择「密钥仓库」），添加文件 `sync-repo-env.yml`：

```yaml
# 限制只有指定仓库可以引用此密钥文件
allow_slugs:
  - 1983shake/sync-repo

GITHUB_TOKEN: github_pat_xxxxxxxxxxxx   # 填入 GitHub PAT
GITHUB_REPO: 1983shake/sync-repo        # 填入 GitHub 仓库路径
```

> **说明**：`allow_slugs` 用于声明哪些仓库可以引用此密钥文件。若省略，则仅密钥仓库的管理员/负责人触发的流水线可以引用。

**开启 CNB 自动触发**
进入 CNB 仓库 -> **设置** -> **云原生构建**，勾选：
- ✅ 允许自动触发
- ✅ Fork 仓库默认允许自动触发（若为 Fork 仓库）

---

## 📄 核心配置文件

### 1. CNB 端 `.cnb.yml`

请将此文件放置在 **`main` 分支的根目录**。

```yaml
# ============================================================================
# CNB 流水线配置
#   功能：
#     1. main 分支 push/commit.add -> 同步到 GitHub main
#     2. release-v* tag -> 建 CNB Release + 同步 tag 到 GitHub + 构建 Docker 镜像
# ============================================================================

"main":
  # 双事件保险：同时配置 push 和 commit.add，避免因事件类型不匹配导致不触发
  push:
    - imports:
        - https://cnb.cool/1983shake/secret-repo/-/blob/main/sync-repo-env.yml
      stages:
        - name: push main to github
          script: |
            set -e
            echo "==> 触发事件: push"
            echo "==> 当前分支: ${CNB_BRANCH}"
            git remote remove github 2>/dev/null || true
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
        - https://cnb.cool/1983shake/secret-repo/-/blob/main/sync-repo-env.yml
      stages:
        - name: prepare release
          script: |
            set -e
            VERSION="${CNB_BRANCH#release-v}"
            echo "版本号: ${VERSION}"
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

```yaml
# ============================================================================
# GitHub Actions：同步 GitHub -> CNB
# ============================================================================
name: Sync to CNB and Create Release

on:
  push:
    branches: [main]
    tags: ['release-v*']
  workflow_dispatch:

permissions:
  contents: write

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

env:
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
          name: Vael-Mux_V${{ steps.version.outputs.VERSION }}
          generate_release_notes: true
```

---

## 🚀 执行流程详解

### 场景一：GitHub 端推送代码到 `main`
1. GitHub Actions 触发 `sync-cnb.yml`。
2. 拉取代码，配置 CNB 远端。
3. 执行 `git push cnb HEAD:main --force`。
4. 代码到达 CNB，触发 CNB 的 `"main"` 流水线。
5. CNB 流水线执行 `git push github HEAD:main --force-with-lease`（由于两端代码已一致，此为 no-op，不会触发 GitHub Actions）。

### 场景二：CNB 端推送代码到 `main`
1. CNB 触发 `.cnb.yml` 中的 `"main"` 事件（`push` 或 `commit.add`）。
2. 拉取 GitHub 最新代码，进行 `git rebase`。
3. 执行 `git push github HEAD:main --force-with-lease`，带重试机制防止并发冲突。
4. 代码到达 GitHub，触发 GitHub Actions（若为 no-op 则不触发）。

### 场景三：GitHub 端打 `release-v*` 标签
1. GitHub Actions 触发 `sync-cnb.yml`。
2. 同步标签到 CNB。
3. GitHub 创建 Release（`softprops/action-gh-release`）。
4. 标签到达 CNB，触发 CNB 的 `"release-v*"` 流水线。
5. CNB 创建自身 Release，构建 Docker 镜像并推送（`:版本号` 和 `:latest`）。

### 场景四：CNB 端打 `release-v*` 标签
1. CNB 触发 `"release-v*"` 流水线。
2. 创建 CNB Release。
3. 同步标签到 GitHub（触发 GitHub Actions 创建 GitHub Release）。
4. 构建 Docker 镜像并推送。

---

## ❓ 常见问题排查（FAQ）

### Q1: CNB 推送代码后工作流没有触发？
**排查清单**：
1. **默认分支名称**：确认 CNB 仓库的默认分支是 `main`。若为 `master`，需将其改为 `main` 或删除 `master` 分支。
2. **配置文件位置**：确保 `.cnb.yml` 已被推送到 `main` 分支的根目录（CNB 只读取当前推送分支的配置）。
3. **自动触发开关**：确认 CNB 仓库 -> 设置 -> 云原生构建中勾选了「允许自动触发」。
4. **事件类型匹配**：CNB 默认查找 `commit.add` 事件，已在配置中同时添加 `push` 和 `commit.add` 双保险。
5. **skip 检测**：检查最近的 commit message 是否包含 `[ci skip]` 或 `[skip ci]`。

### Q2: 报错 `refusing to allow a Personal Access Token to create or update workflow`
**原因**：GitHub PAT 缺少 `Workflows` 权限。
**解决**：进入 GitHub Token 编辑页面，在 **Repository permissions** 中找到 **Workflows**，设置为 **Read and write**。Fine-grained Token 修改后无需重新生成，保存即生效。

### Q3: 报错 `cannot lock ref ... is at ... but expected ...`
**原因**：CNB 和 GitHub 双向同步时发生并发写冲突。
**解决**：已在 `.cnb.yml` 的同步脚本中加入 `git fetch` + `git rebase` + `--force-with-lease` + 重试机制。若仍冲突，可能是两端同时修改了同一文件，需手动介入处理合并冲突。

### Q4: GitHub 出现 "Compare & pull request" 黄色提示
**原因**：CNB 推送到了非默认分支（如 `master`），而 GitHub 的默认分支是 `main`。
**解决**：统一两端默认分支为 `main`。CNB 仓库设置默认分支为 `main`，GitHub 仓库设置默认分支为 `main`，删除旧的 `master` 分支。

### Q5: 密钥仓库的 `allow_slugs` 如何配置？
**解决**：在密钥仓库的 `sync-repo-env.yml` 中，通过 `allow_slugs` 声明哪些仓库可以引用。支持精确匹配（`1983shake/sync-repo`）和通配符（`1983shake/**`）。若省略，则仅密钥仓库管理员/负责人触发的流水线可以引用。

---

## 📋 变量与 Secrets 汇总

| 平台 | 名称 | 存放位置 | 说明 |
|------|------|----------|------|
| GitHub | `GIT_PASSWORD` | Repository Secrets | CNB 访问令牌（仓库写权限） |
| CNB | `GITHUB_TOKEN` | 密钥仓库 `sync-repo-env.yml` | GitHub PAT（`Contents` + `Workflows` 读写） |
| CNB | `GITHUB_REPO` | 密钥仓库 `sync-repo-env.yml` | GitHub 仓库路径，如 `1983shake/sync-repo` |

---

## 💡 最佳实践建议

1. **分支统一**：确保 CNB 和 GitHub 的默认分支均为 `main`，避免分支名不匹配导致同步失败。
2. **权限最小化**：GitHub PAT 仅授予必要权限（`Contents` + `Workflows` + `Metadata`），避免过度授权。
3. **定期轮换 Token**：设置合理的过期时间，定期更新密钥仓库中的 `GITHUB_TOKEN`。
4. **监控流水线**：定期查看 CNB 构建历史和 GitHub Actions 运行记录，及时发现同步异常。
5. **避免自动改写历史**：不要配置自动 amend 或 rebase 后强推的钩子，否则会破坏防循环机制，导致无限同步。
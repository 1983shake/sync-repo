# CNB ⇄ GitHub 双向同步完整配置指南

本文档描述如何在 **CNB** 与 **GitHub** 之间实现代码双向同步、Release 自动创建以及 Docker 镜像自动构建的完整方案。所有需要手动修改的地方，均在代码注释中以 `⚠️ 需要修改` 标注。

---

## 📐 一、整体架构

| 触发端 | 触发事件 | 执行动作 |
|--------|----------|----------|
| **GitHub** | 推送 `main` 分支 | 合并 CNB 独有改动后推送 `main` 到 CNB（GitHub 优先） |
| **GitHub** | 推送 `release-v*` 标签 | 同步标签到 CNB，并在 GitHub 创建 Release |
| **CNB** | 推送 `main` 分支（`push` / `commit.add`） | 合并 GitHub 独有改动后推送 `main` 到 GitHub（CNB 优先） |
| **CNB** | 推送 `release-v*` 标签 | 创建 CNB Release，同步标签到 GitHub，构建并推送 Docker 镜像 |

**防循环机制**：若 Git 推送时 ref 未变化，Git 视为 no-op，不会触发对端 Webhook。请勿在任何一端自动重写提交历史（如 amend），否则会破坏防循环机制。

---

## 🛠️ 二、前置准备

### 1. GitHub 端：创建 Personal Access Token (PAT)

进入 **GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens**，创建 Token 并配置以下权限：

| 权限 | 级别 | 用途 |
|------|------|------|
| **Contents** | Read and write | 推送代码和标签 |
| **Workflows** | Read and write | **必须**，允许推送 `.github/workflows/` 下的文件 |
| **Metadata** | Read-only | 自动勾选，必须 |

> ⚠️ **注意**：仅授予 `Actions: Read and write` **不足以**推送 workflow 文件，必须显式授予 **`Workflows: Read and write`**。

**保存好生成的 Token**（形如 `github_pat_xxxxxxxxxxxx`），后面会填入 CNB 密钥仓库。

### 2. GitHub 端：配置 Actions Secret

进入 GitHub 仓库 → **Settings → Secrets and variables → Actions → New repository secret**，添加：

- **Name**：`GIT_PASSWORD`
- **Value**：CNB 的访问令牌（需具备该 CNB 仓库的写权限）

### 3. CNB 端：创建密钥仓库

在 CNB 创建一个**密钥仓库**（仓库类型必须选择「密钥仓库」），在其中创建文件 `sync-repo-env.yml`：

```yaml
# ============================================================================
# CNB 密钥仓库文件：sync-repo-env.yml
# 用途：存放 GITHUB_TOKEN 和 GITHUB_REPO，供 CNB 流水线 imports 引用
# ============================================================================

# ⚠️ 需要修改：声明哪些 CNB 仓库可以引用此密钥文件
# 支持精确匹配（如 1983shake/sync-repo）和通配符（如 1983shake/**）
# 若省略此项，则仅密钥仓库管理员/负责人触发的流水线可以引用
allow_slugs:
  - 1983shake/sync-repo                # ⚠️ 需要修改：改为你的 CNB 仓库完整 slug

# ⚠️ 需要修改：填入 GitHub PAT
# 类型为 Fine-grained Token，必须包含 Contents 和 Workflows 读写权限
GITHUB_TOKEN: github_pat_xxxxxxxxxxxx

# ⚠️ 需要修改：填入 GitHub 仓库路径（格式：用户名/仓库名）
GITHUB_REPO: 1983shake/sync-repo
```

### 4. CNB 端：开启自动触发

进入 CNB 仓库 → **设置 → 云原生构建**，勾选：

- ✅ 允许自动触发
- ✅ Fork 仓库默认允许自动触发（若为 Fork 仓库）

### 5. 分支统一

确保 CNB 和 GitHub 的**默认分支均为 `main`**：

- **CNB**：仓库设置 → 仓库 → 默认分支改为 `main`
- **GitHub**：仓库 Settings → Branches → Default branch 改为 `main`

---

## 📄 三、配置文件（完整注释版）

### 1. CNB 端：`.cnb.yml`

> 放置在 **CNB 仓库 `main` 分支根目录**。

```yaml
# ============================================================================
# CNB 流水线配置
#   功能：
#     1. main 分支 push / commit.add -> 合并 GitHub 改动后推送 main（CNB 优先）
#     2. release-v* tag -> 建 CNB Release + 同步 tag 到 GitHub + 构建 Docker 镜像
#   引用：密钥仓库 sync-repo-env.yml（提供 GITHUB_TOKEN / GITHUB_REPO）
# ============================================================================

"main":
  # ---------------------------------------------------------------------------
  # 事件：push（任何推送都触发）
  # ---------------------------------------------------------------------------
  push:
    - imports:
        # ⚠️ 需要修改：替换为你的 CNB 密钥仓库文件 URL
        # 格式：https://cnb.cool/<组织>/<密钥仓库名>/-/blob/main/<文件名>.yml
        - https://cnb.cool/1983shake/secret-repo/-/blob/main/sync-repo-env.yml
      stages:
        - name: push main to github (auto-merge + retry)
          script: |
            set -e
            echo "==> 触发事件: push"
            echo "==> 当前分支: ${CNB_BRANCH}"

            # 清理并添加 GitHub 远端
            # ⚠️ 说明：GITHUB_TOKEN / GITHUB_REPO 由 imports 自动注入
            git remote remove github 2>/dev/null || true
            git remote add github \
              "https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPO}.git"

            # 最多重试 5 次，防止并发写冲突
            for i in 1 2 3 4 5; do
              echo "------ 第 ${i} 次尝试 ------"
              git fetch github main || true

              if git rev-parse --verify github/main >/dev/null 2>&1; then
                # 若两端内容一致，直接跳过
                if git diff --quiet HEAD github/main; then
                  echo "✅ CNB 与 GitHub 内容一致，无需同步"
                  exit 0
                fi

                # 合并 GitHub 上的独有改动，冲突时以 CNB 优先（-X ours）
                echo "==> 合并 GitHub 上的独有改动（冲突时 CNB 优先）..."
                if ! git merge --no-edit -X ours github/main; then
                  echo "⚠️ 合并异常，放弃合并，直接用 CNB 覆盖 GitHub"
                  git merge --abort 2>/dev/null || true
                fi
              fi

              echo "==> 推送至 GitHub..."
              if git push github "HEAD:main" --force; then
                echo "✅ 推送成功"
                exit 0
              fi

              echo "⚠️ 推送失败（远端被并发更新），${i} 秒后重试..."
              sleep "$i"
            done

            echo "❌ 推送失败，已达最大重试次数。"
            exit 1

  # ---------------------------------------------------------------------------
  # 事件：commit.add（推送包含新提交时触发，额外提供 CNB_NEW_COMMITS_COUNT）
  # ---------------------------------------------------------------------------
  commit.add:
    - imports:
        # ⚠️ 需要修改：同上，替换为你的密钥仓库文件 URL
        - https://cnb.cool/1983shake/secret-repo/-/blob/main/sync-repo-env.yml
      stages:
        - name: sync new commits to github (auto-merge + retry)
          script: |
            set -e
            echo "==> 触发事件: commit.add"
            echo "==> 当前分支: ${CNB_BRANCH}"
            echo "==> 新增提交数: ${CNB_NEW_COMMITS_COUNT}"

            git remote remove github 2>/dev/null || true
            git remote add github \
              "https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPO}.git"

            for i in 1 2 3 4 5; do
              echo "------ 第 ${i} 次尝试 ------"
              git fetch github main || true

              if git rev-parse --verify github/main >/dev/null 2>&1; then
                if git diff --quiet HEAD github/main; then
                  echo "✅ CNB 与 GitHub 内容一致，无需同步"
                  exit 0
                fi
                echo "==> 合并 GitHub 上的独有改动（冲突时 CNB 优先）..."
                if ! git merge --no-edit -X ours github/main; then
                  echo "⚠️ 合并异常，放弃合并，直接用 CNB 覆盖 GitHub"
                  git merge --abort 2>/dev/null || true
                fi
              fi

              echo "==> 推送至 GitHub..."
              if git push github "HEAD:main" --force; then
                echo "✅ 推送成功"
                exit 0
              fi

              echo "⚠️ 推送失败（远端被并发更新），${i} 秒后重试..."
              sleep "$i"
            done

            echo "❌ 推送失败，已达最大重试次数。"
            exit 1

# ============================================================================
# release-v* 标签流水线：建 Release + 同步 tag + 构建 Docker 镜像
# ============================================================================
"release-v*":
  tag_push:
    - services:
        # 声明需要 Docker 服务，用于后续构建镜像
        - docker
      imports:
        # ⚠️ 需要修改：同上，替换为你的密钥仓库文件 URL
        - https://cnb.cool/1983shake/secret-repo/-/blob/main/sync-repo-env.yml
      stages:
        # -----------------------------------------------------------------
        # 步骤 1：解析版本号与项目名，生成 Release 配置
        # -----------------------------------------------------------------
        - name: prepare release
          script: |
            set -e
            # 从 GITHUB_REPO 中提取项目名（如 1983shake/sync-repo -> sync-repo）
            PROJECT_NAME="${GITHUB_REPO##*/}"
            # 兜底：若 GITHUB_REPO 为空，则使用 CNB 仓库名
            if [ -z "$PROJECT_NAME" ]; then
              PROJECT_NAME="${CNB_REPO_NAME:-${CNB_REPO_SLUG##*/}}"
            fi
            # 从 tag 名（release-v1.0.0）中剥离前缀，得到版本号（1.0.0）
            VERSION="${CNB_BRANCH#release-v}"
            echo "项目名: ${PROJECT_NAME}"
            echo "版本号: ${VERSION}"

            # ⚠️ 说明：标题模板可自定义，{PROJECT_NAME}_V{VERSION} 仅为默认格式
            cat > release-options.json <<EOF
            {
              "title": "${PROJECT_NAME}_V${VERSION}",
              "description": "Release ${PROJECT_NAME} V${VERSION}"
            }
            EOF
            echo "生成的 Release 配置："
            cat release-options.json

        # -----------------------------------------------------------------
        # 步骤 2：调用 CNB 内置动作创建 Release
        # -----------------------------------------------------------------
        - name: create release on cnb
          type: git:release
          optionsFrom: ./release-options.json

        # -----------------------------------------------------------------
        # 步骤 3：将 tag 同步到 GitHub（触发 GitHub 侧创建 Release）
        # -----------------------------------------------------------------
        - name: sync tag to github
          script: |
            set -e
            echo "==> 同步 tag ${CNB_BRANCH} 到 GitHub"
            git remote remove github 2>/dev/null || true
            git remote add github \
              "https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPO}.git"

            for i in 1 2 3 4 5; do
              if git push github \
                "refs/tags/${CNB_BRANCH}:refs/tags/${CNB_BRANCH}" --force; then
                echo "✅ tag 推送成功"
                exit 0
              fi
              echo "⚠️ tag 推送失败，${i} 秒后重试..."
              sleep "$i"
            done
            echo "❌ tag 推送失败"
            exit 1

        # -----------------------------------------------------------------
        # 步骤 4：构建并推送 Docker 镜像（:版本号 与 :latest）
        # -----------------------------------------------------------------
        - name: docker build and push
          script: |
            set -e
            # ⚠️ 说明：IMAGE_BASE 使用 CNB 内置的镜像仓库地址，无需手动修改
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

### 2. GitHub 端：`.github/workflows/sync-cnb.yml`

> 放置在 **GitHub 仓库 `main` 分支的 `.github/workflows/` 目录下**。

```yaml
# ============================================================================
# GitHub Actions：同步 GitHub -> CNB
#   功能：
#     1. 推送 main 分支 -> 合并 CNB 独有改动后推送 main（GitHub 优先）
#     2. 推送 release-v* tag -> 同步 tag 到 CNB + 在 GitHub 创建 Release
#   依赖：Repository Secret `GIT_PASSWORD`（CNB 访问令牌）
# ============================================================================
name: Sync to CNB and Create Release

on:
  push:
    branches: [main]                # 监听 main 分支推送
    tags: ['release-v*']            # 监听 release-v* 标签
  workflow_dispatch:                # 支持手动触发

permissions:
  contents: write                   # 需要写权限创建 Release

# 并发控制：同一 workflow + ref 仅保留最新一次运行
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

env:
  # ⚠️ 需要修改：替换为你的 CNB 仓库地址（必须以 .git 结尾）
  CNB_REPO: cnb.cool/1983shake/sync-repo.git

jobs:
  sync:
    runs-on: ubuntu-latest
    timeout-minutes: 10

    steps:
      # ----------------------------------------------------------------------
      # 步骤 1：拉取完整历史（fetch-depth: 0 保证能 fetch 到所有 ref）
      # ----------------------------------------------------------------------
      - name: Checkout code
        uses: actions/checkout@v5
        with:
          fetch-depth: 0

      # ----------------------------------------------------------------------
      # 步骤 2：配置 Git 与 CNB 远端
      #   GIT_PASSWORD 来自 GitHub Repository Secrets
      # ----------------------------------------------------------------------
      - name: Configure Git and CNB remote
        run: |
          git config --global user.name "GitHub Action"
          git config --global user.email "action@github.com"
          git remote remove cnb 2>/dev/null || true
          git remote add cnb \
            "https://cnb:${{ secrets.GIT_PASSWORD }}@${{ env.CNB_REPO }}"

      # ----------------------------------------------------------------------
      # 步骤 3：从 tag 中提取版本号和项目名（仅 tag 推送时执行）
      # ----------------------------------------------------------------------
      - name: Extract version and project name from tag
        id: version
        if: startsWith(github.ref, 'refs/tags/release-v')
        run: |
          VERSION="${GITHUB_REF_NAME#release-v}"
          PROJECT_NAME="${GITHUB_REPOSITORY##*/}"
          echo "VERSION=${VERSION}" >> "$GITHUB_OUTPUT"
          echo "PROJECT_NAME=${PROJECT_NAME}" >> "$GITHUB_OUTPUT"
          echo "版本号: ${VERSION}"
          echo "项目名: ${PROJECT_NAME}"

      # ----------------------------------------------------------------------
      # 步骤 4：同步 main 分支到 CNB（合并 CNB 独有改动 + 重试）
      # ----------------------------------------------------------------------
      - name: Push main branch to CNB (auto-merge + retry)
        if: github.ref == 'refs/heads/main'
        run: |
          set -e
          echo "==> 同步 main 到 CNB"

          for i in 1 2 3 4 5; do
            echo "------ 第 ${i} 次尝试 ------"
            git fetch cnb main || true

            if git rev-parse --verify cnb/main >/dev/null 2>&1; then
              if git diff --quiet HEAD cnb/main; then
                echo "✅ GitHub 与 CNB 内容一致，无需同步"
                exit 0
              fi

              # 合并 CNB 独有改动，冲突时以 GitHub 优先（-X ours）
              echo "==> 合并 CNB 上的独有改动（冲突时 GitHub 优先）..."
              if ! git merge --no-edit -X ours cnb/main; then
                echo "⚠️ 合并异常，放弃合并，直接用 GitHub 覆盖 CNB"
                git merge --abort 2>/dev/null || true
              fi
            fi

            echo "==> 推送至 CNB..."
            if git push cnb HEAD:main --force; then
              echo "✅ 推送成功"
              exit 0
            fi

            echo "⚠️ 推送失败（远端被并发更新），${i} 秒后重试..."
            sleep "$i"
          done

          echo "❌ 推送失败，已达最大重试次数。"
          exit 1

      # ----------------------------------------------------------------------
      # 步骤 5：同步 tag 到 CNB（触发 CNB 侧构建 Docker 镜像）
      # ----------------------------------------------------------------------
      - name: Push tag to CNB
        if: startsWith(github.ref, 'refs/tags/release-v')
        run: |
          echo "==> 同步 tag ${GITHUB_REF_NAME} 到 CNB"
          for i in 1 2 3 4 5; do
            if git push cnb \
              "refs/tags/${GITHUB_REF_NAME}:refs/tags/${GITHUB_REF_NAME}" --force; then
              echo "✅ tag 推送成功"
              exit 0
            fi
            echo "⚠️ tag 推送失败，${i} 秒后重试..."
            sleep "$i"
          done
          echo "❌ tag 推送失败"
          exit 1

      # ----------------------------------------------------------------------
      # 步骤 6：在 GitHub 端创建 Release
      #   ⚠️ 需要修改：name 模板可自定义，默认使用 {PROJECT_NAME}_V{VERSION}
      # ----------------------------------------------------------------------
      - name: Create GitHub Release
        if: startsWith(github.ref, 'refs/tags/release-v')
        uses: softprops/action-gh-release@v3
        with:
          tag_name: ${{ github.ref_name }}
          name: ${{ steps.version.outputs.PROJECT_NAME }}_V${{ steps.version.outputs.VERSION }}
          generate_release_notes: true
```

---

## 🔄 四、执行流程详解

### 场景 1：GitHub 端推送 `main`
1. GitHub Actions 触发 `sync-cnb.yml`。
2. **拉取 CNB 的 `main` 并合并**（冲突时 GitHub 优先）。
3. 推送合并后的结果到 CNB（重试 5 次）。
4. CNB 收到推送，触发 `push` / `commit.add`。
5. CNB 侧检测到两端内容已一致，**直接退出**（不产生回推）。

### 场景 2：CNB 端推送 `main`
1. CNB 触发 `.cnb.yml` 的 `"main"` 流水线。
2. **拉取 GitHub 的 `main` 并合并**（冲突时 CNB 优先）。
3. 推送合并后的结果到 GitHub（重试 5 次）。
4. GitHub Actions 检测到推送，触发 `sync-cnb.yml`。
5. GitHub 侧检测到两端内容已一致，**直接退出**。

### 场景 3：GitHub 端打 `release-v*` 标签
1. GitHub Actions 同步 tag 到 CNB。
2. GitHub 端创建 Release。
3. CNB 收到 tag，触发 `"release-v*"` 流水线。
4. CNB 侧创建 Release、同步 tag 回 GitHub、**构建并推送 Docker 镜像**。

### 场景 4：CNB 端打 `release-v*` 标签
1. CNB 侧创建 Release。
2. 同步 tag 到 GitHub（触发 GitHub 创建 Release）。
3. **构建并推送 Docker 镜像**。

---

## ❓ 五、常见问题排查

### Q1：CNB 推送代码后工作流没有触发？
排查以下 4 项：
1. **默认分支**：CNB 仓库默认分支是否为 `main`？
2. **配置文件位置**：`.cnb.yml` 是否在 `main` 分支根目录？
3. **自动触发开关**：是否勾选「允许自动触发」？
4. **commit message**：是否包含 `[ci skip]` / `[skip ci]`？

### Q2：报错 `refusing to allow a Personal Access Token to create or update workflow`
**原因**：GitHub PAT 缺少 `Workflows` 权限。
**解决**：进入 Token 编辑页面，在 Repository permissions 中找到 **Workflows**，设为 **Read and write**。Fine-grained Token 修改后保存即生效，无需重新生成。

### Q3：报错 `cannot lock ref ... is at ... but expected ...`
**原因**：CNB 与 GitHub 双向同步时发生并发写冲突。
**解决**：当前配置已内置 **`git fetch` + `git merge` + `--force` + 重试 5 次** 机制。若仍失败，说明两端同时修改了同一文件，需手动介入解决冲突。

### Q4：GitHub 出现 "Compare & pull request" 黄色提示
**原因**：CNB 推送到了非默认分支（如 `master`）。
**解决**：统一两端默认分支为 `main`。

### Q5：`imports` 引用失败
**检查点**：
1. 密钥仓库路径是否正确（`https://cnb.cool/<组织>/<仓库>/-/blob/main/<文件>.yml`）。
2. `allow_slugs` 是否包含当前 CNB 仓库的完整 slug。
3. 密钥文件是否为 YAML 键值对格式。

---

## 📋 六、配置汇总表

| 平台 | 名称 | 存放位置 | 备注 |
|------|------|----------|------|
| GitHub | `GIT_PASSWORD` | Repository Secrets | CNB 访问令牌（仓库写权限） |
| CNB | `GITHUB_TOKEN` | 密钥仓库 `sync-repo-env.yml` | GitHub PAT（`Contents` + `Workflows` 读写） |
| CNB | `GITHUB_REPO` | 密钥仓库 `sync-repo-env.yml` | GitHub 仓库路径，如 `1983shake/sync-repo` |
| CNB | `allow_slugs` | 密钥仓库 `sync-repo-env.yml` | 授权引用该密钥的 CNB 仓库白名单 |

---

## 💡 七、最佳实践

1. **分支统一**：确保 CNB 和 GitHub 默认分支均为 `main`。
2. **权限最小化**：GitHub PAT 仅授予 `Contents` + `Workflows` + `Metadata`。
3. **定期轮换 Token**：设置合理过期时间，及时更新密钥仓库。
4. **监控流水线**：定期检查 CNB 构建历史与 GitHub Actions 运行记录。
5. **避免自动 amend**：不要在任何一端配置自动 amend 或强推钩子，否则会破坏防循环机制。
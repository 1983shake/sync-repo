# CNB ⇄ GitHub 双向同步、Release 与 Docker 镜像构建指南

本文档描述如何基于 `.cnb.yml` 与 `sync-cnb.yml` 实现 **CNB 与 GitHub 双向同步、Release 自动创建、Docker 镜像自动构建**。  
所有需要根据自己环境修改的地方，均以 `⚠️ 需要修改` 标注。

---

## 一、功能介绍

| 触发端 | 触发事件 | 执行动作 |
|--------|----------|----------|
| **CNB** | `main` 分支 `push` / `commit.add` | 拉取 GitHub `main`，合并 GitHub 独有改动（冲突时 **CNB 优先**），强制推送 `main` 到 GitHub，失败自动重试 5 次 |
| **GitHub** | `main` 分支 `push` | 拉取 CNB `main`，合并 CNB 独有改动（冲突时 **GitHub 优先**），强制推送 `main` 到 CNB，失败自动重试 5 次 |
| **CNB** | `release-v*` 标签 `tag_push` | ① 从 CNB / GitHub 获取 Release 描述<br>② 创建 / 规范化 CNB Release（标题 `<项目名>_V<版本号>`）<br>③ 同步标签到 GitHub<br>④ 构建并推送 Docker 镜像（`:版本号` 与 `:latest`） |
| **GitHub** | `release-v*` 标签 `push` | ① 从 CNB 拉取该标签 Release 描述<br>② 创建 GitHub Release（标题 `<项目名>_V<版本号>`，描述优先 CNB，为空则自动生成 notes）<br>③ 推送标签到 CNB（触发 CNB 侧 Release + Docker 构建） |

**防循环机制**：任一方向推送后，对端拉取并合并；若两端内容一致，则直接退出，不产生回推。  
**描述来源优先级**：  
- CNB 创建 Release 时：先查 CNB 侧已有 Release 描述 → 再查 GitHub 侧该标签 Release 描述。  
- GitHub 创建 Release 时：先查 CNB 侧描述 → 若为空则自动生成 notes。  
- 整体上，**CNB 网页手动填写的描述优先**；若 CNB 无描述，则使用 GitHub 侧描述。

---

## 二、使用流程

### 1. 准备授权与密钥

**GitHub 端**  
- 创建 Fine-grained Personal Access Token（PAT），权限见第四节。  
- 在 GitHub 仓库 `Settings → Secrets and variables → Actions` 添加 Secret：  
  - `GIT_PASSWORD`：CNB 访问令牌（具备 CNB 仓库写权限）。

**CNB 端**  
- 创建 **密钥仓库**（类型必须选「密钥仓库」），新建文件 `sync-repo-env.yml`，内容见第五节完整注释文件。  
- 在 CNB 仓库 `设置 → 云原生构建` 中勾选：  
  - ✅ 允许自动触发  
  - ✅ Fork 仓库默认允许自动触发（若为 Fork）

### 2. 放置配置文件

| 文件 | 放置位置 | 说明 |
|------|----------|------|
| `.cnb.yml` | CNB 仓库 `main` 分支根目录 | CNB 流水线配置 |
| `sync-cnb.yml` | GitHub 仓库 `.github/workflows/` 目录 | GitHub Actions 配置 |
| `sync-repo-env.yml` | CNB 密钥仓库 | 存放 `GITHUB_TOKEN` 与 `GITHUB_REPO`，供 `.cnb.yml` 通过 `imports` 引用 |

### 3. 统一默认分支

确保 **CNB 与 GitHub 的默认分支均为 `main`**。  
- CNB：仓库设置 → 默认分支改为 `main`  
- GitHub：仓库 Settings → Branches → Default branch 改为 `main`

### 4. 触发与执行流程

#### 场景 A：CNB 推送 `main`
1. CNB 触发 `.cnb.yml` 的 `"main"` 流水线。  
2. 拉取 GitHub `main`，合并独有改动（冲突时 CNB 优先）。  
3. 强制推送 `main` 到 GitHub（重试 5 次）。  
4. GitHub Actions 被触发，检测两端内容一致，直接退出，不回推。

#### 场景 B：GitHub 推送 `main`
1. GitHub Actions 触发 `sync-cnb.yml`。  
2. 拉取 CNB `main`，合并独有改动（冲突时 GitHub 优先）。  
3. 强制推送 `main` 到 CNB（重试 5 次）。  
4. CNB 流水线被触发，检测两端内容一致，直接退出。

#### 场景 C：GitHub 打 `release-v*` 标签
1. GitHub Actions 提取版本号与项目名。  
2. 从 CNB API 拉取该标签的 Release 描述。  
3. **先创建 GitHub Release**（标题 `<项目名>_V<版本号>`，描述优先 CNB，为空则自动生成 notes）。  
4. 推送标签到 CNB。  
5. CNB 触发 `"release-v*"` 流水线：  
   - 从 CNB / GitHub 获取描述，创建 CNB Release。  
   - 同步标签回 GitHub（通常 no-op）。  
   - 构建并推送 Docker 镜像。

#### 场景 D：CNB 打 `release-v*` 标签
1. CNB 触发 `"release-v*"` 流水线。  
2. 从 CNB / GitHub 获取描述，创建 CNB Release。  
3. 推送标签到 GitHub。  
4. GitHub Actions 触发：从 CNB 拉取描述，创建 GitHub Release。  
5. CNB 继续构建并推送 Docker 镜像。

### 5. 完整注释文件

#### 5.1 CNB 密钥仓库文件 `sync-repo-env.yml`

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

#### 5.2 CNB 流水线配置 `.cnb.yml`

```yaml
# ============================================================================
# 可修改变量（只改这里）
# ============================================================================
x-vars:
  # ⚠️ 需要修改：CNB 密钥仓库文件 URL
  secret_repo_url: &secret_repo_url "https://cnb.cool/1983shake/secret-repo/-/blob/main/sync-repo-env.yml"

  github_repo: &github_repo "1983shake/sync-repo"
  cnb_repo: &cnb_repo "cnb.cool/1983shake/sync-repo.git"

# ============================================================================
# CNB 流水线配置
#   功能：
#     1. main 分支 push / commit.add -> 合并 GitHub 改动后推送 main（CNB 优先）
#     2. release-v* tag ->
#          描述来源优先级：
#            a) CNB 侧已存在的 Release 描述（用户在 CNB 网页上填写）
#            b) GitHub 侧该 tag 的 Release 描述（用户在 GitHub 网页上填写）
#          使用该描述创建/更新 CNB Release，标题规范化为 "<项目名>_V<版本号>"
#          + 同步 tag 到 GitHub + 构建 Docker 镜像
# ============================================================================

# ============================================================================
# main 分支同步
# ============================================================================
"main":
  push:
    - imports:
        - *secret_repo_url
      stages:
        - name: push main to github (auto-merge + retry)
          script: |
            set -e
            echo "==> 触发事件: push"
            echo "==> 当前分支: ${CNB_BRANCH}"

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

  commit.add:
    - imports:
        - *secret_repo_url
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
# release-v* 标签流水线
#   描述获取优先级：
#     1. CNB 侧该 tag 已存在的 Release（用户在 CNB 网页上填写）
#     2. GitHub 侧该 tag 的 Release（用户在 GitHub 网页上填写）
#   用途：
#     - 用该描述创建/更新 CNB Release（标题规范化为 "<项目名>_V<版本号>"）
#     - 同步 tag 到 GitHub
#     - 构建并推送 Docker 镜像
# ============================================================================
"release-v*":
  tag_push:
    - services:
        - docker
      imports:
        - *secret_repo_url
      stages:
        # -----------------------------------------------------------------
        # 步骤 1：生成 release-options.json（描述来源：CNB → GitHub 依次兜底）
        # -----------------------------------------------------------------
        - name: prepare release options
          script: |
            set -e

            TAG_NAME="${CNB_TAG:-$CNB_BRANCH}"
            PROJECT_NAME="${GITHUB_REPO##*/}"
            VERSION="${TAG_NAME#release-v}"
            NEW_TITLE="${PROJECT_NAME}_V${VERSION}"

            echo "==> TAG:      ${TAG_NAME}"
            echo "==> 项目名:   ${PROJECT_NAME}"
            echo "==> 版本号:   ${VERSION}"
            echo "==> 目标标题: ${NEW_TITLE}"

            # ---------- JSON 工具探测 ----------
            JSON_TOOL=""
            if   command -v jq      >/dev/null 2>&1; then JSON_TOOL=jq
            elif command -v python3 >/dev/null 2>&1; then JSON_TOOL=python3
            elif command -v python  >/dev/null 2>&1; then JSON_TOOL=python
            fi
            echo "==> JSON 工具: ${JSON_TOOL:-无}"

            # ---------- 统一的 JSON 描述提取函数（jq / python 双实现）----------
            extract_desc_from_file() {
              # 参数1: JSON 文件路径
              # 参数2: 目标 tag
              # 参数3: 字段优先级（从高到低，空格分隔），如 "body description desc notes"
              local file="$1"
              local tag="$2"
              local fields="$3"

              if [ "${JSON_TOOL}" = "jq" ]; then
                jq -r --arg tag "${tag}" --arg fields "${fields}" '
                  (if type=="array" then . else (.releases // []) end)
                  | map(select((.tag_name // .tag)==$tag))
                  | (.[0] // {})
                  | ( [ .body, .description, .desc, .notes ] | map(select(. != null and . != "")) | .[0] // "" )
                ' "${file}" 2>/dev/null || true
              else
                "${JSON_TOOL}" -c '
            import json, sys
            file, tag = sys.argv[1], sys.argv[2]
            try:
                with open(file) as f:
                    data = json.load(f)
            except Exception:
                sys.exit(0)
            items = data if isinstance(data, list) else (data or {}).get("releases", [])
            for r in items:
                if r.get("tag_name") == tag or r.get("tag") == tag:
                    sys.stdout.write(
                        r.get("body") or r.get("description")
                        or r.get("desc") or r.get("notes") or ""
                    )
                    break
                ' "${file}" "${tag}" 2>/dev/null || true
              fi
            }

            # ---------- 提取单个 GitHub Release JSON 的描述（顶层 body）----------
            extract_body_from_gh() {
              local file="$1"
              if [ "${JSON_TOOL}" = "jq" ]; then
                jq -r '.body // ""' "${file}" 2>/dev/null || true
              else
                "${JSON_TOOL}" -c '
            import json, sys
            try:
                with open(sys.argv[1]) as f:
                    data = json.load(f)
            except Exception:
                sys.exit(0)
            sys.stdout.write(data.get("body") or "")
                ' "${file}" 2>/dev/null || true
              fi
            }

            DESC=""

            # -----------------------------------------------------------------
            # 来源 1：CNB 侧该 tag 的 Release 描述（若用户在 CNB 网页上填了）
            # -----------------------------------------------------------------
            if [ -n "${JSON_TOOL}" ] && [ -n "${CNB_API_ENDPOINT}" ] && [ -n "${CNB_REPO_SLUG}" ]; then
              URL="${CNB_API_ENDPOINT}/${CNB_REPO_SLUG}/-/releases"
              echo "==> [来源 1] 拉取 CNB Releases: ${URL}"

              CODE="$(curl -s -o /tmp/cnb-releases.json -w '%{http_code}' \
                -H "Authorization: Bearer ${CNB_TOKEN}" \
                -H "accept: application/json" \
                "${URL}" 2>/dev/null || echo 000)"
              echo "==> CNB API HTTP: ${CODE}"

              if [ "${CODE}" = "200" ]; then
                DESC="$(extract_desc_from_file /tmp/cnb-releases.json "${TAG_NAME}" "body description desc notes")"
                echo "==> CNB 提取到的描述长度: ${#DESC}"
              fi
            fi

            # -----------------------------------------------------------------
            # 来源 2：GitHub 侧该 tag 的 Release 描述（GitHub 触发场景）
            #   只有在来源 1 为空时才去 GitHub 拿，避免覆盖 CNB 上手动填的描述
            # -----------------------------------------------------------------
            if [ -z "${DESC}" ] && [ -n "${JSON_TOOL}" ] && [ -n "${GITHUB_TOKEN}" ] && [ -n "${GITHUB_REPO}" ]; then
              GH_URL="https://api.github.com/repos/${GITHUB_REPO}/releases/tags/${TAG_NAME}"
              echo "==> [来源 2] 拉取 GitHub Release: ${GH_URL}"

              CODE="$(curl -s -o /tmp/gh-release.json -w '%{http_code}' \
                -H "Authorization: Bearer ${GITHUB_TOKEN}" \
                -H "accept: application/vnd.github+json" \
                -H "X-GitHub-Api-Version: 2022-11-28" \
                "${GH_URL}" 2>/dev/null || echo 000)"
              echo "==> GitHub API HTTP: ${CODE}"

              if [ "${CODE}" = "200" ]; then
                DESC="$(extract_body_from_gh /tmp/gh-release.json)"
                echo "==> GitHub 提取到的描述长度: ${#DESC}"
              fi
            fi

            if [ -z "${DESC}" ]; then
              echo "⚠️ 两个来源均未获取到描述，CNB Release 描述将为空"
            fi

            # ---------- 生成 release-options.json（单行，合法 JSON）----------
            if [ "${JSON_TOOL}" = "jq" ]; then
              jq -n \
                --arg tag "$TAG_NAME" \
                --arg title "$NEW_TITLE" \
                --arg description "$DESC" \
                '{tag: $tag, title: $title, description: $description}' \
                > release-options.json
            elif [ -n "${JSON_TOOL}" ]; then
              "${JSON_TOOL}" -c '
            import json, sys
            json.dump(
                {"tag": sys.argv[1], "title": sys.argv[2], "description": sys.argv[3]},
                open("release-options.json", "w"),
                ensure_ascii=False,
            )
            ' "$TAG_NAME" "$NEW_TITLE" "$DESC"
            else
              echo "❌ 环境缺少 jq/python，无法生成 JSON"
              exit 1
            fi

            echo "==> 生成的 release-options.json:"
            cat release-options.json
            echo

        # -----------------------------------------------------------------
        # 步骤 2：用 optionsFrom 读取 JSON，创建/规范化 CNB Release
        # -----------------------------------------------------------------
        - name: create / normalize cnb release
          type: git:release
          optionsFrom: ./release-options.json

        # -----------------------------------------------------------------
        # 步骤 3：同步 tag 到 GitHub
        #   （若由 GitHub 触发，这一步通常是 no-op，因为 tag 已存在）
        # -----------------------------------------------------------------
        - name: sync tag to github
          script: |
            set -e
            TAG_NAME="${CNB_TAG:-$CNB_BRANCH}"

            echo "==> 同步 tag ${TAG_NAME} 到 GitHub"
            git remote remove github 2>/dev/null || true
            git remote add github \
              "https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPO}.git"

            for i in 1 2 3 4 5; do
              if git push github \
                "refs/tags/${TAG_NAME}:refs/tags/${TAG_NAME}" --force; then
                echo "✅ tag 推送成功"
                exit 0
              fi
              echo "⚠️ tag 推送失败，${i} 秒后重试..."
              sleep "$i"
            done
            echo "❌ tag 推送失败"
            exit 1

        # -----------------------------------------------------------------
        # 步骤 4：构建并推送 Docker 镜像
        # -----------------------------------------------------------------
        - name: docker build and push
          script: |
            set -e
            TAG_NAME="${CNB_TAG:-$CNB_BRANCH}"
            IMAGE_BASE="${CNB_DOCKER_REGISTRY}/${CNB_REPO_SLUG_LOWERCASE}"
            VERSION="${TAG_NAME#release-v}"
            echo "==> 构建版本: ${VERSION}"

            # ⚠️ 可选：把版本号注入镜像时取消注释，并在 Dockerfile 声明 ARG APP_VERSION
            # docker build --build-arg APP_VERSION="${VERSION}" \
            docker build \
              -t "${IMAGE_BASE}:${VERSION}" \
              -t "${IMAGE_BASE}:latest" \
              .
            docker push "${IMAGE_BASE}:${VERSION}"
            docker push "${IMAGE_BASE}:latest"
            echo "==> 镜像推送完成: ${IMAGE_BASE}:${VERSION}"
```

#### 5.3 GitHub Actions 配置 `sync-cnb.yml`

```yaml
# ============================================================================
# GitHub Actions：同步 GitHub -> CNB
#   功能：
#     1. 推送 main 分支 -> 合并 CNB 独有改动后推送 main（GitHub 优先）
#     2. 推送 release-v* tag ->
#          a) 先从 CNB 拉取该 tag 的 Release 描述（若存在）
#          b) 在 GitHub 创建 Release（名称 "<项目名>_V<版本号>"，
#             描述优先使用 CNB 侧描述，若 CNB 无描述则自动生成 notes）
#          c) 再把 tag 推送到 CNB
#          d) CNB 侧收到 tag 后，会通过 GitHub API 反查描述并创建 CNB Release
#   依赖：
#     - Repository Secret: GIT_PASSWORD（CNB 访问令牌，具备仓库写权限）
#   触发时机：
#     - main 分支 push
#     - release-v* 标签 push
#     - 手动触发（workflow_dispatch）
# ============================================================================
name: Sync to CNB and Create Release

on:
  push:
    branches: [main]                # 监听 main 分支推送
    tags: ['release-v*']            # 监听 release-v* 标签
  workflow_dispatch:                # 支持在 Actions 页面手动触发

# 需要写权限才能在 tag 推送时创建 Release
permissions:
  contents: write

# 并发控制：同一 workflow + ref 只保留最新一次运行，避免同时推送冲突
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

env:
  # ⚠️ 需要修改：替换为你的 CNB 仓库地址（必须以 .git 结尾）
  CNB_REPO: cnb.cool/1983shake/sync-repo.git

  # ⚠️ 需要修改：存放 CNB 访问令牌的 GitHub Secret 名称
  CNB_TOKEN_SECRET_NAME: GIT_PASSWORD

  # CNB API 地址（按你的 CNB 实际 API 地址修改）
  CNB_API_ENDPOINT: https://api.cnb.cool

jobs:
  sync:
    runs-on: ubuntu-latest
    timeout-minutes: 10

    steps:
      # ----------------------------------------------------------------------
      # 步骤 1：拉取完整历史
      # ----------------------------------------------------------------------
      - name: Checkout code
        uses: actions/checkout@v5
        with:
          fetch-depth: 0

      # ----------------------------------------------------------------------
      # 步骤 2：配置 Git 用户信息与 CNB 远端
      # ----------------------------------------------------------------------
      - name: Configure Git and CNB remote
        run: |
          git config --global user.name "GitHub Action"
          git config --global user.email "action@github.com"
          git remote remove cnb 2>/dev/null || true
          git remote add cnb \
            "https://cnb:${{ secrets[env.CNB_TOKEN_SECRET_NAME] }}@${{ env.CNB_REPO }}"

      # ----------------------------------------------------------------------
      # 步骤 3：从 tag 中提取版本号和项目名
      #   tag = release-v1.2.3 -> VERSION=1.2.3, PROJECT_NAME=<仓库名>
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
      # 步骤 4：同步 main 分支到 CNB（含自动合并 + 重试）
      #   仅在 main 分支推送时执行
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
      # 步骤 5：从 CNB 拉取 Release 描述
      #   仅在 tag 推送时执行
      #   优先使用 CNB 侧该 tag 的 Release 描述；
      #   若 CNB 侧没有描述，则后续 GitHub Release 自动生成 notes。
      # ----------------------------------------------------------------------
      - name: Fetch CNB Release description
        id: cnb_release
        if: startsWith(github.ref, 'refs/tags/release-v')
        env:
          CNB_TOKEN: ${{ secrets[env.CNB_TOKEN_SECRET_NAME] }}
        run: |
          set -e
          TAG_NAME="${GITHUB_REF_NAME}"

          # 从 CNB_REPO 中提取仓库 slug，例如 1983shake/sync-repo
          CNB_REPO_SLUG="${CNB_REPO#cnb.cool/}"
          CNB_REPO_SLUG="${CNB_REPO_SLUG%.git}"

          URL="${CNB_API_ENDPOINT}/${CNB_REPO_SLUG}/-/releases"
          echo "==> 从 CNB 获取 Release 描述: ${URL}"
          echo "==> 目标 tag: ${TAG_NAME}"

          BODY=""
          for i in 1 2 3 4 5; do
            CODE="$(curl -sS -o /tmp/cnb-releases.json -w '%{http_code}' \
              -H "Authorization: Bearer ${CNB_TOKEN}" \
              -H "accept: application/json" \
              "${URL}" || echo 000)"
            echo "==> 第 ${i} 次 CNB API HTTP: ${CODE}"

            if [ "${CODE}" = "200" ]; then
              if command -v jq >/dev/null 2>&1; then
                BODY="$(jq -r --arg tag "${TAG_NAME}" '
                  (if type=="array" then . else (.releases // []) end)
                  | map(select((.tag_name // .tag) == $tag))
                  | (.[0] // {})
                  | ([.body, .description, .desc, .notes] | map(select(. != null and . != "")) | .[0] // "")
                ' /tmp/cnb-releases.json)"
              else
                echo "⚠️ 未找到 jq，无法解析 CNB 响应，将使用空描述。"
                BODY=""
              fi

              if [ -n "${BODY}" ]; then
                echo "==> 已获取 CNB 描述，长度: ${#BODY}"
                break
              fi
            fi

            echo "⚠️ 未获取到 CNB 描述，${i} 秒后重试..."
            sleep "$i"
          done

          if [ -z "${BODY}" ]; then
            echo "⚠️ CNB 侧没有找到该 tag 的 Release 描述，将使用自动生成 notes。"
          fi

          {
            echo "body<<__CNB_BODY_EOF__"
            printf '%s\n' "${BODY}"
            echo "__CNB_BODY_EOF__"
          } >> "$GITHUB_OUTPUT"

      # ----------------------------------------------------------------------
      # 步骤 6：在 GitHub 端创建 Release
      #   ⚠️ 关键时序：必须在 "Push tag to CNB" 之前执行！
      #     因为 CNB 收到 tag 后会立刻通过 GitHub API 反查此 Release 的描述，
      #     若此处还没建好，CNB 侧就只能拿到空描述。
      #
      #   仅在 tag 推送时执行
      #   name 使用 "{项目名}_V{版本号}" 格式，与 CNB 侧 Release 命名保持一致
      #   描述优先使用从 CNB 拉取的 body，若为空则自动生成 notes
      # ----------------------------------------------------------------------
      - name: Create GitHub Release
        id: gh_release
        if: startsWith(github.ref, 'refs/tags/release-v')
        uses: softprops/action-gh-release@v3
        with:
          tag_name: ${{ github.ref_name }}
          name: ${{ steps.version.outputs.PROJECT_NAME }}_V${{ steps.version.outputs.VERSION }}
          body: ${{ steps.cnb_release.outputs.body }}
          generate_release_notes: ${{ steps.cnb_release.outputs.body == '' }}
          overwrite_files: true

      # ----------------------------------------------------------------------
      # 步骤 7：同步 tag 到 CNB
      #   仅在 tag 推送时执行
      #   精确推送指定 ref，避免使用 --tags 误推其他历史 tag
      #   CNB 收到 tag 后会触发 release-v* 流水线：
      #     1) 通过 GitHub API 反查此 tag 的 Release 描述
      #     2) 用该描述创建 CNB Release（标题规范化 "<项目名>_V<版本号>"）
      #     3) 构建并推送 Docker 镜像
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
```

---

## 三、注意事项

1. **默认分支必须统一为 `main`**  
   CNB 和 GitHub 的默认分支都必须是 `main`，否则会出现 “Compare & pull request” 提示或同步异常。

2. **防循环机制**  
   两端推送后都会拉取对端并比较内容，若一致则直接退出，不会产生回推。  
   **不要在任何一端配置自动 `amend` 或强推钩子**，否则会破坏防循环机制。

3. **Release 描述优先级与时序**  
   - CNB 创建 Release：优先 CNB 侧已有描述 → 其次 GitHub 侧该标签描述。  
   - GitHub 创建 Release：先拉取 CNB 侧描述 → 为空则自动生成 notes。  
   - GitHub Actions 中 **必须先创建 GitHub Release，再推送 tag 到 CNB**，否则 CNB 反查不到描述。

4. **Docker 镜像构建**  
   仅在 CNB 的 `release-v*` 流水线中执行。  
   镜像标签为 `${CNB_DOCKER_REGISTRY}/${CNB_REPO_SLUG_LOWERCASE}:${VERSION}` 和 `:latest`。  
   若需注入版本号，取消 `--build-arg APP_VERSION` 注释，并在 Dockerfile 中声明 `ARG APP_VERSION`。

5. **重试机制**  
   所有 Git 推送均内置 5 次重试，每次间隔递增。若仍失败，通常是因为两端同时修改了同一文件，需手动解决冲突。

6. **CNB 自动触发**  
   确保 CNB 仓库设置中已勾选「允许自动触发」，否则 `.cnb.yml` 不会执行。

7. **密钥仓库 `allow_slugs`**  
   必须包含当前 CNB 仓库的完整 slug（如 `1983shake/sync-repo`），否则 `imports` 引用失败。

8. **GitHub PAT 的 Workflows 权限**  
   若推送内容包含 `.github/workflows/` 下的文件，GitHub PAT 必须具有 **Workflows: Read and write** 权限，否则报错 `refusing to allow a Personal Access Token to create or update workflow`。

---

## 四、推荐的授权方式

### 1. GitHub Fine-grained PAT（用于 CNB → GitHub）

| 权限 | 级别 | 用途 |
|------|------|------|
| **Contents** | Read and write | 推送代码和标签 |
| **Workflows** | Read and write | **必须**，允许推送 `.github/workflows/` 下的文件 |
| **Metadata** | Read-only | 自动勾选，必须 |

> 该 Token 填入 CNB 密钥仓库的 `GITHUB_TOKEN` 字段。

### 2. CNB 访问令牌（用于 GitHub → CNB）

- 需具备目标 CNB 仓库的 **写权限**。
- 在 GitHub 仓库中保存为 Secret：`GIT_PASSWORD`。
- `sync-cnb.yml` 中通过 `secrets[env.CNB_TOKEN_SECRET_NAME]` 引用，默认名称为 `GIT_PASSWORD`。

### 3. CNB 密钥仓库（`sync-repo-env.yml`）

- 仓库类型必须为「密钥仓库」。
- 文件内容为 YAML 键值对，至少包含：
  - `allow_slugs`：授权引用该密钥的 CNB 仓库白名单。
  - `GITHUB_TOKEN`：GitHub PAT。
  - `GITHUB_REPO`：GitHub 仓库路径，如 `1983shake/sync-repo`。
- 在 `.cnb.yml` 中通过 `imports` 引用该文件的 URL。

### 4. 权限最小化建议

- GitHub PAT 仅授予 `Contents` + `Workflows` + `Metadata`。
- CNB 访问令牌仅授予目标仓库写权限。
- 定期轮换 Token，并及时更新密钥仓库与 GitHub Secret。
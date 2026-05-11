# PyTo Code Commit Command

## 概述

`pyto commit` 命令实现了完整的 Git 提交和合并请求（MR）创建流程，基于您提供的 Agent Skill 规范。

## 使用方法

### 基本用法

```bash
# 运行完整的提交流程
uv run pyto commit

# 或者
python -m pyto_code commit

# 跳过代码审核确认（不推荐）
uv run pyto commit --skip-review
```

## 流程步骤

### 1. 代码审核清单
- 显示完整的代码审核清单
- 包含代码质量、功能完整性、测试覆盖、安全性、性能检查
- 需要用户逐项确认后才能继续

### 2. 暂存更改
- 检查当前 Git 状态
- 询问是否暂存所有更改或指定特定文件
- 执行 `git add` 操作

### 3. 提交代码
- 引导用户输入符合规范的提交信息
- 格式：`<type>(<scope>): <subject>`
- 支持详细的提交描述
- 预览提交信息并确认

### 4. 同步 prepare 分支
- 自动 fetch 远程更改
- 切换到 prepare 分支并拉取最新代码
- 合并 prepare 分支到当前功能分支
- 处理合并冲突（如有）

### 5. 推送到远程
- 推送当前分支到远程仓库
- 验证推送成功

### 6. 创建合并请求
- 检查 glab（GitLab CLI）认证状态
- 创建目标为 `prepare` 分支的 MR
- 自动在浏览器中打开 MR 页面
- 返回格式化的 MR 链接：`[MR !<编号>: <标题>](<URL>)`

## 配置要求

### GitLab 配置
命令使用以下默认配置：
- GitLab 主机：`192.168.1.54`
- GitLab 端口：`8008`
- 仓库名称：`yugu/yugu_yxpt`

### GitLab CLI (glab)
需要安装并配置 GitLab CLI：
```bash
# 安装 glab
# macOS: brew install glab
# Ubuntu: sudo apt install glab
# 或从 https://gitlab.com/gitlab-org/cli/releases 下载

# 登录 GitLab
glab auth login -p http --hostname 192.168.1.54
```

## 提交信息规范

### 提交类型
- `feat:` 新功能
- `fix:` 错误修复
- `refactor:` 代码重构
- `docs:` 文档更新
- `style:` 代码格式调整
- `test:` 测试相关
- `chore:` 维护任务

### 示例
```bash
feat(auth): 添加用户认证功能

- 实现 JWT 令牌生成
- 添加密码哈希验证
- 创建认证中间件
```

## 错误处理

### Git 所有权问题
如果遇到 "detected dubious ownership" 错误：
```bash
git config --global --add safe.directory '/path/to/your/repo'
```

### 推送被拒绝
```bash
# 先拉取远程更改
git pull origin feature/your-feature-name

# 或强制推送（谨慎使用）
git push --force-with-lease origin feature/your-feature-name
```

### MR 创建失败
- 检查 glab 认证状态：`glab auth status --hostname 192.168.1.54`
- 重新登录：`glab auth login -p http --hostname 192.168.1.54`
- 确认分支已推送到远程

## 最佳实践

1. **代码质量**：确保代码符合项目编码规范
2. **测试覆盖**：包含必要的单元测试
3. **提交粒度**：每个提交只做一件事
4. **同步策略**：提交 MR 前必须同步 prepare 分支
5. **代码审查**：所有代码必须经过审查

## 完整示例

```bash
$ uv run pyto commit

🚀 开始 Git 提交和 MR 创建流程
============================================================

📋 CODE REVIEW CHECKLIST
============================================================

🔍 代码质量检查:
  □ 代码符合项目编码规范
  □ 函数和变量命名清晰
  □ 注释充分且准确
  □ 没有调试代码和 console.log
  □ 没有硬编码的配置值

🔍 功能完整性检查:
  □ 功能实现符合需求
  □ 边界条件已处理
  □ 错误处理机制完善
  □ 用户体验良好

...

请逐项检查上述清单，确认无误后继续 [y/N]: y

📁 检查当前状态...
On branch feature/user-auth
Your branch is up to date with 'origin/feature/user-auth'.

Changes to be committed:
  modified:   src/auth.py
  modified:   tests/test_auth.py

是否要添加所有更改到暂存区？ [y/N]: y
✅ 文件已暂存

📝 提交信息规范:
格式: <type>(<scope>): <subject>
类型: feat, fix, refactor, docs, style, test, chore
示例: feat(auth): 添加用户认证功能

请输入提交标题: feat(auth): 添加用户认证功能
请输入详细描述（可选，按回车跳过）: 实现 JWT 令牌生成和密码验证

📋 提交信息预览:
----------------------------------------
feat(auth): 添加用户认证功能

实现 JWT 令牌生成和密码验证
----------------------------------------
确认使用此提交信息？ [y/N]: y
✅ 代码已提交

🔄 同步 prepare 分支...
✅ 已同步 prepare 分支

✅ 已推送分支 feature/user-auth 到远程

🔐 请先登录 GitLab:
glab auth login -p http --hostname 192.168.1.54
登录完成后是否继续？ [y/N]: y

🌐 已自动打开 MR 页面: http://192.168.1.54:8008/yugu/yugu_yxpt/-/merge_requests/123
✅ MR 创建成功!
📋 [MR !123: 添加用户认证功能](http://192.168.1.54:8008/yugu/yugu_yxpt/-/merge_requests/123)

📝 等待代码审查和合并...

🎉 流程完成!
```

## 故障排除

### 常见问题

1. **glab 命令未找到**
   - 确保已安装 GitLab CLI
   - 检查 PATH 环境变量

2. **Git 认证失败**
   - 检查 SSH 密钥配置
   - 验证 GitLab 访问权限

3. **MR 目标分支错误**
   - 确保目标分支是 `prepare`，不是 `master`
   - 检查分支保护规则

4. **浏览器未自动打开**
   - 手动访问显示的 MR 链接
   - 检查默认浏览器设置

## 技术实现

该命令基于以下技术实现：
- **Python subprocess**：执行 Git 和 GitLab 命令
- **argparse**：CLI 参数解析
- **webbrowser**：自动打开 MR 页面
- **Path**：文件路径处理

## 扩展性

可以通过修改 `GitWorkflow` 类来：
- 调整 GitLab 配置
- 自定义审核清单
- 添加更多提交类型
- 集成其他 CI/CD 工具

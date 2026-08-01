"""Git submit workflow — commit, push, and create merge request."""

import asyncio
import subprocess
import sys
import webbrowser
from typing import Optional, Tuple

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from .commit import GitWorkflow


class MRContent(BaseModel):
    title: str = Field(description="Merge request title")
    description: str = Field(description="Merge request description")


class SubmitWorkflow(GitWorkflow):
    """Git workflow automation for commit, push, and MR creation."""

    def _get_mr_prompt(self) -> str:
        """Get MR content generation prompt based on language configuration."""
        if self.language == "en":
            return """You are a professional Merge Request content generation assistant. Please generate concise titles and detailed descriptions based on the provided code change information and commit history.

MR Title Requirements:
- Concise and clear, not exceeding 60 characters
- Accurately summarize the main changes
- Use English for titles
- Avoid overly technical terms
- Highlight the value and purpose of changes

MR Description Requirements:
- Detailed explanation of change background and purpose
- List main changes and features
- Explain impact scope
- Provide testing suggestions or verification methods
- Use English for descriptions
- Clear format, easy to read
- Use Markdown format

Description Structure:
## Background
Explain why this change is needed

## Main Changes
List specific features or modifications

## Impact Scope
Explain which modules or functions will be affected

## Testing Suggestions
Provide suggestions on how to verify the changes

Example Titles:
- Add user authentication functionality
- Fix login page display issue
- Optimize database query performance
- Refactor order processing logic

Please generate both concise accurate titles and detailed structured descriptions."""
        else:  # Default to Chinese
            return """你是一个专业的 Merge Request 内容生成助手。请根据提供的代码变更信息和提交记录生成简洁的标题和详细的描述。

MR 标题要求：
- 简洁明了，不超过60个字符
- 准确概括本次变更的主要内容
- 使用中文生成标题
- 避免过于技术化的术语
- 突出变更的价值和目的

MR 描述要求：
- 详细说明变更的背景和目的
- 列出主要的变更内容和功能
- 说明变更的影响范围
- 提供测试建议或验证方法
- 使用中文生成描述
- 格式清晰，易于阅读
- 使用 Markdown 格式

描述结构建议：
## 变更背景
说明为什么需要这个变更

## 主要变更
列出具体的功能或修改内容

## 影响范围
说明哪些模块或功能会受到影响

## 测试建议
提供如何验证变更效果的建议

示例标题：
- 添加用户认证功能
- 修复登录页面显示问题
- 优化数据库查询性能
- 重构订单处理逻辑

请同时生成简洁准确的标题和详细结构化的描述。"""

    def _setup_commit_agent(self):
        super()._setup_commit_agent()

        self.mr_agent = Agent(
            self.model,
            output_type=MRContent,
            system_prompt=self._get_mr_prompt(),
        )

    async def generate_mr_content(self, branch: str) -> Tuple[str, str]:
        """Generate MR title and description using LLM based on branch changes and commit history."""
        self.console.print("\n🤖 正在分析分支变更并生成 MR 标题和描述...", style="cyan")

        try:
            diff_result = self.run_command(
                [
                    "git",
                    "diff",
                    "--stat",
                    f"origin/{self.develop_branch}...origin/{branch}",
                ]
            )
            detailed_diff = self.run_command(
                ["git", "diff", f"origin/{self.develop_branch}...origin/{branch}"]
            )

            files_result = self.run_command(
                [
                    "git",
                    "diff",
                    "--name-only",
                    f"origin/{self.develop_branch}...origin/{branch}",
                ]
            )
            changed_files = (
                files_result.stdout.strip().split("\n")
                if files_result.stdout.strip()
                else []
            )

            try:
                commit_log = self.run_command(
                    [
                        "git",
                        "log",
                        "--pretty=format:%h %s",
                        "--no-merges",
                        f"origin/{self.develop_branch}..origin/{branch}",
                    ]
                )
                commit_messages = commit_log.stdout.strip()

                detailed_commits = self.run_command(
                    [
                        "git",
                        "log",
                        "--pretty=format:%h%n%s%n%b",
                        "--no-merges",
                        f"origin/{self.develop_branch}..origin/{branch}",
                    ]
                )
                detailed_commit_info = detailed_commits.stdout.strip()
            except subprocess.CalledProcessError:
                commit_messages = ""
                detailed_commit_info = ""

            context = f"""
分支名称: {branch}
目标分支: {self.develop_branch}

代码变更统计：
{diff_result.stdout}

变更文件列表：
{chr(10).join(changed_files)}

提交记录：
{commit_messages}

详细提交信息：
{detailed_commit_info[:2000]}

详细变更内容：
{detailed_diff.stdout[:2000]}

请基于以上分支变更信息同时生成简洁的标题和详细的描述。
"""

            result = await self.mr_agent.run(context)
            mr_title = result.output.title
            mr_description = result.output.description

            self.console.print("\n🤖 AI 生成的 MR 标题:", style="cyan")
            title_panel = Panel(mr_title, title="标题", border_style="green")
            self.console.print(title_panel)

            self.console.print("\n🤖 AI 生成的 MR 描述:", style="cyan")
            desc_panel = Panel(mr_description, title="描述", border_style="green")
            self.console.print(desc_panel)

            return mr_title, mr_description

        except Exception as e:
            self.console.print(f"⚠️  AI 生成 MR 内容失败: {e}", style="yellow")
            self.console.print("回退到手动输入模式...", style="yellow")
            return self._fallback_mr_content(branch)

    def _fallback_mr_content(self, branch: str) -> Tuple[str, str]:
        """Fallback method for manual MR title and description input."""
        if self.language == "en":
            self.console.print("\n📝 MR Content Guidelines:", style="cyan")
            self.console.print("Title Requirements:")
            self.console.print("- Concise and clear, not exceeding 60 characters")
            self.console.print("- Accurately summarize changes")
            self.console.print("- Use English titles")
            self.console.print("Description Requirements:")
            self.console.print(
                "- Detailed explanation of change background and purpose"
            )
            self.console.print("- List main changes and features")
            self.console.print("- Explain impact scope")
            self.console.print("- Provide testing suggestions or verification methods")
            self.console.print("- Use Markdown format")

            while True:
                title = input("\nEnter MR title: ").strip()
                if not title:
                    self.console.print("❌ MR title cannot be empty", style="red")
                    continue

                self.console.print(
                    "\nEnter MR description (Markdown supported, type 'END' to finish):"
                )
                lines = []
                while True:
                    line = input()
                    if line.strip() == "END":
                        break
                    lines.append(line)

                description = "\n".join(lines).strip()
                if not description:
                    self.console.print("❌ MR description cannot be empty", style="red")
                    continue

                self.console.print("\n📋 MR Content Preview:", style="cyan")
                title_panel = Panel(title, title="Title Preview", border_style="yellow")
                self.console.print(title_panel)

                desc_panel = Panel(
                    description, title="Description Preview", border_style="yellow"
                )
                self.console.print(desc_panel)

                if self.confirm("Confirm using this MR title and description?"):
                    return title, description
                self.console.print("Please re-enter...", style="yellow")
        else:  # Default to Chinese
            self.console.print("\n📝 MR 内容规范:", style="cyan")
            self.console.print("标题要求:")
            self.console.print("- 简洁明了，不超过60个字符")
            self.console.print("- 准确概括变更内容")
            self.console.print("- 使用中文标题")
            self.console.print("描述要求:")
            self.console.print("- 详细说明变更的背景和目的")
            self.console.print("- 列出主要的变更内容和功能")
            self.console.print("- 说明变更的影响范围")
            self.console.print("- 提供测试建议或验证方法")
            self.console.print("- 使用 Markdown 格式")

            while True:
                title = input("\n请输入 MR 标题: ").strip()
                if not title:
                    self.console.print("❌ MR 标题不能为空", style="red")
                    continue

                self.console.print(
                    "\n请输入 MR 描述（支持 Markdown，输入 'END' 结束）:"
                )
                lines = []
                while True:
                    line = input()
                    if line.strip() == "END":
                        break
                    lines.append(line)

                description = "\n".join(lines).strip()
                if not description:
                    self.console.print("❌ MR 描述不能为空", style="red")
                    continue

                self.console.print("\n📋 MR 内容预览:", style="cyan")
                title_panel = Panel(title, title="标题预览", border_style="yellow")
                self.console.print(title_panel)

                desc_panel = Panel(description, title="描述预览", border_style="yellow")
                self.console.print(desc_panel)

                if self.confirm("确认使用此 MR 标题和描述？"):
                    return title, description
                self.console.print("请重新输入...", style="yellow")

    def get_mr_content(self, branch: str) -> Tuple[str, str]:
        """Get MR title and description (now using LLM generation)."""
        return asyncio.run(self.generate_mr_content(branch))

    def check_glab_auth(self) -> bool:
        """Check if glab is authenticated."""
        try:
            result = self.run_command(
                ["glab", "auth", "status", "--hostname", self.gitlab_host], check=False
            )
            return result.returncode == 0
        except FileNotFoundError:
            self.console.print("❌ 未找到 glab 命令，请先安装 GitLab CLI", style="red")
            return False

    def create_merge_request(self, branch: str) -> Optional[str]:
        """Create merge request and return MR URL."""
        if not self.check_glab_auth():
            self.console.print("🔐 请先登录 GitLab:", style="yellow")
            self.console.print(
                f"glab auth login -p http --hostname {self.gitlab_host}", style="cyan"
            )
            if not self.confirm("登录完成后是否继续？"):
                return None

        try:
            title, description = self.get_mr_content(branch)

            cmd = [
                "glab",
                "mr",
                "create",
                "--repo",
                self.repo_name,
                "--target-branch",
                self.develop_branch,
                "--source-branch",
                branch,
                "--title",
                title,
                "--description",
                description,
                "-y",
            ]

            result = self.run_command(cmd)

            self.console.print("MR result.stdout: %s" % result.stdout)
            mr_url = result.stdout
            try:
                webbrowser.open(mr_url)
                self.console.print(f"🌐 已自动打开 MR 页面: {mr_url}", style="green")
            except:  # noqa: E722
                self.console.print(f"📎 MR 链接: {mr_url}", style="cyan")
            return mr_url

        except subprocess.CalledProcessError as e:
            self.console.print(f"❌ 创建 MR 失败: {e}", style="red")
            return None

    def cleanup(self, branch: str) -> None:
        """Cleanup after successful merge."""
        self.console.print(f"\n🧹 清理分支 {branch}...", style="cyan")

        try:
            self.run_command(["git", "checkout", self.develop_branch])
            self.run_command(["git", "pull", "origin", self.develop_branch])
            self.run_command(["git", "branch", "-d", branch])
            self.run_command(["git", "push", "origin", "--delete", branch])
            self.console.print(f"✅ 已清理分支 {branch}", style="green")
        except subprocess.CalledProcessError as e:
            self.console.print(f"⚠️  清理失败: {e}", style="yellow")


def submit(args) -> None:
    """Handle the submit command — full workflow: commit, push, and create MR."""
    workflow = SubmitWorkflow()

    workflow.console.print("🚀 开始 Git 提交和 MR 创建流程", style="bold green")
    workflow.console.print("=" * 60, style="blue")

    # Check if there are changes to commit
    if not workflow.check_git_status():
        workflow.console.print("ℹ️  没有需要提交的更改", style="cyan")
        sys.exit(0)

    # Stage changes
    if not workflow.stage_changes():
        workflow.console.print("❌ 暂存失败，终止流程", style="red")
        sys.exit(1)

    # Get commit message and commit
    commit_msg = workflow.get_commit_message()
    if not workflow.commit_changes(commit_msg):
        workflow.console.print("❌ 提交失败，终止流程", style="red")
        sys.exit(1)

    # Check branch divergence and decide on sync strategy
    current_branch = workflow.get_current_branch()
    should_sync, analysis = workflow.should_sync_develop_branch(current_branch)

    # Display analysis results
    workflow.display_divergence_analysis(analysis)

    # Make sync decision based on analysis
    if should_sync:
        if not workflow.sync_develop_branch():
            workflow.console.print("❌ 同步失败，终止流程", style="red")
            sys.exit(1)
    else:
        workflow.console.print("✅ 跳过同步，直接提交 MR", style="green")

    # Push to remote
    if not workflow.push_to_remote(current_branch):
        workflow.console.print("❌ 推送失败，终止流程", style="red")
        sys.exit(1)

    # Create MR
    mr_link = workflow.create_merge_request(current_branch)
    if mr_link:
        workflow.console.print("\n✅ MR 创建成功!", style="bold green")
        workflow.console.print(f"📋 {mr_link}", style="cyan")
        workflow.console.print("\n📝 等待代码审查和合并...", style="yellow")
    else:
        workflow.console.print("❌ MR 创建失败", style="red")
        sys.exit(1)

    workflow.console.print("\n🎉 流程完成!", style="bold green")

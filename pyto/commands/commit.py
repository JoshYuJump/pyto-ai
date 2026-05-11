"""Git commit and merge request workflow implementation."""

import os
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Optional

import toml
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.prompt import Confirm


class GitWorkflow:
    """Git workflow automation for commit and MR creation."""

    def __init__(self):
        self.console = Console()
        self.config = self._load_config()

        # 从配置文件读取设置
        gitflow_config = self.config.get("gitflow", {})
        self.gitlab_host = gitflow_config.get("gitlab_host", "")
        self.gitlab_port = gitflow_config.get("gitlab_port", "")
        self.repo_name = gitflow_config.get("repo_name", "")
        self.develop_branch = gitflow_config.get("develop_branch", "develop")

    def _load_config(self) -> dict:
        """Load configuration from pyto.toml."""
        config_path = Path("pyto.toml")

        if not config_path.exists():
            self.console.print("⚠️  未找到 pyto.toml 配置文件", style="yellow")
            self.console.print("正在创建默认配置文件...", style="cyan")
            self._create_default_config(config_path)
            self.console.print("✅ 已创建 pyto.toml 配置文件", style="green")
            self.console.print("📝 请根据需要更新配置文件中的设置", style="yellow")

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return toml.load(f)
        except Exception as e:
            self.console.print(f"❌ 读取配置文件失败: {e}", style="red")
            self.console.print("使用默认配置", style="yellow")
            return {}

    def _create_default_config(self, config_path: Path) -> None:
        """Create default pyto.toml configuration file."""
        default_config = """# PyTo Code Configuration File
# PyTo Code - A lightweight, extensible Python-first Code Agent framework

[gitflow]
# GitLab 配置
gitlab_host = "your.gitlab.local"
gitlab_port = "80"
repo_name = "repo_path/repo_name"

# 分支配置
develop_branch = "develop"  # GitFlow 中的 develop 分支
"""
        config_path.write_text(default_config, encoding="utf-8")

    def run_command(
        self, cmd: list[str], check: bool = True
    ) -> subprocess.CompletedProcess:
        """Run a command and return the result."""
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=check)
            return result
        except subprocess.CalledProcessError as e:
            self.console.print(
                f"❌ Error running command: {' '.join(cmd)}", style="red"
            )
            self.console.print(f"STDERR: {e.stderr}", style="red")
            raise

    def confirm(self, message: str) -> bool:
        """Get user confirmation."""
        return Confirm.ask(f"{message}", default=False)

    def get_current_branch(self) -> str:
        """Get the current git branch name."""
        result = self.run_command(["git", "rev-parse", "--abbrev-ref", "HEAD"])
        return result.stdout.strip()

    def check_git_status(self) -> bool:
        """Check if there are changes to commit."""
        try:
            result = self.run_command(["git", "status", "--porcelain"])
            return bool(result.stdout.strip())
        except subprocess.CalledProcessError as e:
            if "detected dubious ownership" in e.stderr:
                self.console.print("❌ Git 检测到仓库所有权问题", style="red")
                self.console.print("请运行以下命令解决:", style="yellow")
                self.console.print(
                    f"git config --global --add safe.directory '{os.getcwd()}'",
                    style="cyan",
                )
            else:
                self.console.print(f"❌ Git 状态检查失败: {e.stderr}", style="red")
            sys.exit(1)

    
    def stage_changes(self) -> bool:
        """Stage changes for commit."""
        self.console.print("\n📁 检查当前状态...", style="cyan")
        result = self.run_command(["git", "status"])
        self.console.print(result.stdout)

        if not Confirm.ask("是否要添加所有更改到暂存区？", default=True):
            # Let user specify files interactively
            files_input = self.console.input("请输入要暂存的文件路径（用空格分隔）: ")
            if files_input:
                files = files_input.split()
                for file_path in files:
                    self.run_command(["git", "add", file_path])
            else:
                self.console.print("❌ 未暂存任何文件", style="red")
                return False
        else:
            self.run_command(["git", "add", "."])

        self.console.print("✅ 文件已暂存", style="green")
        return True

    def get_commit_message(self) -> str:
        """Get commit message from user."""
        self.console.print("\n📝 提交信息规范:", style="cyan")
        self.console.print("格式: <type>(<scope>): <subject>")
        self.console.print("类型: feat, fix, refactor, docs, style, test, chore")
        self.console.print("示例: feat(auth): 添加用户认证功能")

        while True:
            subject = input("\n请输入提交标题: ").strip()
            if not subject:
                self.console.print("❌ 提交标题不能为空", style="red")
                continue

            body = input("请输入详细描述（可选，按回车跳过）: ").strip()

            commit_msg = subject
            if body:
                commit_msg += f"\n\n{body}"

            self.console.print("\n📋 提交信息预览:", style="cyan")
            panel = Panel(commit_msg, title="预览", border_style="yellow")
            self.console.print(panel)

            if self.confirm("确认使用此提交信息？"):
                return commit_msg
            self.console.print("请重新输入...", style="yellow")

    def commit_changes(self, message: str) -> bool:
        """Commit staged changes."""
        try:
            self.run_command(["git", "commit", "-m", message])
            self.console.print("✅ 代码已提交", style="green")
            return True
        except subprocess.CalledProcessError:
            self.console.print("❌ 提交失败", style="red")
            return False

    def sync_develop_branch(self) -> bool:
        """Sync with develop branch."""
        self.console.print(f"\n🔄 同步 {self.develop_branch} 分支...", style="cyan")

        try:
            # Fetch latest changes
            self.run_command(["git", "fetch", "origin"])

            # Checkout and pull develop branch
            self.run_command(["git", "checkout", self.develop_branch])
            self.run_command(["git", "pull", "origin", self.develop_branch])

            # Go back to feature branch
            current_branch = self.get_current_branch()
            self.run_command(["git", "checkout", current_branch])

            # Merge develop into feature branch
            try:
                self.run_command(["git", "merge", self.develop_branch])
                self.console.print(
                    f"✅ 已同步 {self.develop_branch} 分支", style="green"
                )
                return True
            except subprocess.CalledProcessError:
                self.console.print("⚠️  合并冲突，请手动解决后继续", style="yellow")
                if not self.confirm("是否已解决冲突并继续？"):
                    return False
                self.run_command(["git", "add", "."])
                self.run_command(
                    [
                        "git",
                        "commit",
                        "-m",
                        f"resolve: 合并 {self.develop_branch} 分支的更改",
                    ]
                )
                return True

        except subprocess.CalledProcessError as e:
            self.console.print(f"❌ 同步失败: {e}", style="red")
            return False

    def push_to_remote(self, branch: str) -> bool:
        """Push branch to remote."""
        try:
            self.run_command(["git", "push", "origin", branch])
            self.console.print(f"✅ 已推送分支 {branch} 到远程", style="green")
            return True
        except subprocess.CalledProcessError:
            self.console.print(f"❌ 推送分支 {branch} 失败", style="red")
            return False

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
            # Create MR with develop as target branch
            title = input("请输入 MR 标题: ").strip() or branch
            cmd = [
                "glab",
                "mr",
                "create",
                "--fill",
                "--repo",
                self.repo_name,
                "--target-branch",
                self.develop_branch,
                "--source-branch",
                branch,
                "--title",
                title,
                "-y",
            ]

            result = self.run_command(cmd)

            # Extract MR number from output
            import re

            mr_match = re.search(r"!(\d+)", result.stdout)
            if mr_match:
                mr_number = mr_match.group(1)
                mr_url = f"http://{self.gitlab_host}:{self.gitlab_port}/{self.repo_name}/-/merge_requests/{mr_number}"

                # Auto-open browser
                try:
                    webbrowser.open(mr_url)
                    self.console.print(
                        f"🌐 已自动打开 MR 页面: {mr_url}", style="green"
                    )
                except:  # noqa: E722
                    self.console.print(f"📎 MR 链接: {mr_url}", style="cyan")

                return f"[MR !{mr_number}: {title}]({mr_url})"

            self.console.print("⚠️  无法获取 MR 编号", style="yellow")
            return None

        except subprocess.CalledProcessError as e:
            self.console.print(f"❌ 创建 MR 失败: {e}", style="red")
            return None

    def cleanup(self, branch: str) -> None:
        """Cleanup after successful merge."""
        self.console.print(f"\n🧹 清理分支 {branch}...", style="cyan")

        try:
            # Switch to develop branch
            self.run_command(["git", "checkout", self.develop_branch])
            self.run_command(["git", "pull", "origin", self.develop_branch])

            # Delete local branch
            self.run_command(["git", "branch", "-d", branch])

            # Delete remote branch
            self.run_command(["git", "push", "origin", "--delete", branch])

            self.console.print(f"✅ 已清理分支 {branch}", style="green")
        except subprocess.CalledProcessError as e:
            self.console.print(f"⚠️  清理失败: {e}", style="yellow")


def commit(args) -> None:
    """Handle the commit command."""
    workflow = GitWorkflow()

    workflow.console.print("🚀 开始 Git 提交和 MR 创建流程", style="bold green")
    workflow.console.print("=" * 60, style="blue")

    # Check if there are changes to commit
    if not workflow.check_git_status():
        workflow.console.print("ℹ️  没有需要提交的更改", style="cyan")
        sys.exit(0)

    # Step 2: Stage changes
    if not workflow.stage_changes():
        workflow.console.print("❌ 暂存失败，终止流程", style="red")
        sys.exit(1)

    # Step 3: Get commit message and commit
    commit_msg = workflow.get_commit_message()
    if not workflow.commit_changes(commit_msg):
        workflow.console.print("❌ 提交失败，终止流程", style="red")
        sys.exit(1)

    # Step 4: Sync with develop branch
    if not workflow.sync_develop_branch():
        workflow.console.print("❌ 同步失败，终止流程", style="red")
        sys.exit(1)

    # Step 5: Push to remote
    current_branch = workflow.get_current_branch()
    if not workflow.push_to_remote(current_branch):
        workflow.console.print("❌ 推送失败，终止流程", style="red")
        sys.exit(1)

    # Step 6: Create MR
    mr_link = workflow.create_merge_request(current_branch)
    if mr_link:
        workflow.console.print("\n✅ MR 创建成功!", style="bold green")
        workflow.console.print(f"📋 {mr_link}", style="cyan")
        workflow.console.print("\n📝 等待代码审查和合并...", style="yellow")
    else:
        workflow.console.print("❌ MR 创建失败", style="red")
        sys.exit(1)

    workflow.console.print("\n🎉 流程完成!", style="bold green")

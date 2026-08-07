"""Git commit and push workflow implementation."""

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from subprocess import CompletedProcess

import toml
from pydantic import BaseModel, Field
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm

from pyto.llm import create_agent


class CommitMessage(BaseModel):
    message: str = Field(description="Git commit message")


class GitWorkflow:
    """Git workflow automation for commit and push."""

    def __init__(self):
        self.console = Console(force_terminal=True, legacy_windows=False)
        self.config = self._load_config()

        gitflow_config = self.config.get("gitflow", {})
        self.gitlab_host = gitflow_config.get("gitlab_host", "")
        self.gitlab_port = gitflow_config.get("gitlab_port", "")
        self.repo_name = gitflow_config.get("repo_name", "")
        self.develop_branch = gitflow_config.get("develop_branch", "develop")

        general_config = self.config.get("general", {})
        self.language = general_config.get("language", "zh")

        self.working_branch = self.get_current_branch()

        self.divergence_threshold = 20
        self.file_change_threshold = 10
        self.long_lived_branch_days = 14

        self.commit_agent = create_agent(
            output_type=CommitMessage,
            system_prompt=self._get_commit_prompt(),
        )

    def _get_commit_prompt(self) -> str:
        """Get commit message generation prompt based on language configuration."""
        if self.language == "en":
            return """You are a professional Git commit message generation assistant. Please generate standardized commit messages based on the provided code change information.

Commit message format:
- Type(type): feat, fix, refactor, docs, style, test, chore
- Scope(scope): Optional, describe the affected module or component
- Subject(subject): Concise description, not exceeding 50 characters
- Body(body): Optional, detailed description of changes and reasons
- Generate commit messages in English

Example format:
feat(auth): add user authentication functionality

- Implement JWT token validation
- Add login/registration endpoints
- Integrate permission middleware

Please generate concise, accurate, and standardized commit messages."""
        else:  # Default to Chinese
            return """你是一个专业的 Git 提交信息生成助手。请根据提供的代码变更信息生成符合规范的提交信息。

提交信息格式规范：
- 类型(type): feat, fix, refactor, docs, style, test, chore
- 范围(scope): 可选，说明影响的模块或组件
- 主题(subject): 简洁描述，不超过50个字符
- 正文(body): 可选，详细描述变更内容和原因
- 使用中文生成提交信息

示例格式：
feat(auth): 添加用户认证功能

- 实现JWT token验证
- 添加登录/注册接口
- 集成权限中间件

请生成简洁、准确、符合规范的提交信息。"""

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

[general]
# 语言配置 (language configuration)
# 支持的语言: "zh" (中文), "en" (英文)
# Supported languages: "zh" (Chinese), "en" (English)
language = "zh"

[gitflow]
# GitLab 配置
gitlab_host = "your.gitlab.local"
gitlab_port = "80"
repo_name = "repo_path/repo_name"

# 分支配置
develop_branch = "develop"  # GitFlow 中的 develop 分支
"""
        config_path.write_text(default_config, encoding="utf-8")

    def run_command(self, cmd: list[str], check: bool = True) -> CompletedProcess:
        """Run a command and return the result."""
        try:
            res: CompletedProcess = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=check,
            )
            return res
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

    def get_commit_divergence(
        self, branch: str, target_branch: str = None
    ) -> tuple[int, int]:
        """Get commit divergence between branches."""
        if target_branch is None:
            target_branch = self.develop_branch

        try:
            self.run_command(["git", "fetch", "origin"])

            cmd = [
                "git",
                "rev-list",
                "--left-right",
                "--count",
                f"origin/{target_branch}...origin/{branch}",
            ]
            result = self.run_command(cmd)

            counts = result.stdout.strip().split()
            if len(counts) == 2:
                return int(counts[0]), int(counts[1])
            return 0, 0

        except subprocess.CalledProcessError:
            self.console.print("❌ 无法获取分支差异信息", style="red")
            return 0, 0

    def get_changed_files(self, branch: str, target_branch: str = None) -> list[str]:
        """Get list of changed files between branches."""
        if target_branch is None:
            target_branch = self.develop_branch

        try:
            self.run_command(["git", "fetch", "origin"])

            cmd = [
                "git",
                "diff",
                "--name-only",
                f"origin/{target_branch}...origin/{branch}",
            ]
            result = self.run_command(cmd)

            return [f.strip() for f in result.stdout.split("\n") if f.strip()]

        except subprocess.CalledProcessError:
            self.console.print("❌ 无法获取改动文件列表", style="red")
            return []

    def analyze_file_changes(self, files: list[str]) -> dict:
        """Analyze file changes to determine conflict probability."""
        import re

        analysis = {
            "total_files": len(files),
            "core_modules": 0,
            "backend_files": 0,
            "migration_files": 0,
            "directory_changes": {},
            "high_conflict_risk": False,
        }

        core_patterns = [
            r"^src/core/",
            r"^lib/core/",
            r"^app/core/",
            r"^models/",
            r"^services/",
            r"^api/",
            r"^config/",
            r"^database/",
        ]

        backend_patterns = [
            r"\.py$",
            r"\.js$",
            r"\.ts$",
            r"\.go$",
            r"\.java$",
            r"^backend/",
            r"^server/",
            r"^app/",
        ]

        migration_patterns = [r"migration", r"schema", r"database", r"seed"]

        for file_path in files:
            for pattern in core_patterns:
                if re.search(pattern, file_path, re.IGNORECASE):
                    analysis["core_modules"] += 1
                    analysis["high_conflict_risk"] = True
                    break

            for pattern in backend_patterns:
                if re.search(pattern, file_path):
                    analysis["backend_files"] += 1
                    break

            for pattern in migration_patterns:
                if re.search(pattern, file_path, re.IGNORECASE):
                    analysis["migration_files"] += 1
                    analysis["high_conflict_risk"] = True
                    break

            directory = Path(file_path).parent.as_posix()
            analysis["directory_changes"][directory] = (
                analysis["directory_changes"].get(directory, 0) + 1
            )

        for count in analysis["directory_changes"].values():
            if count > self.file_change_threshold:
                analysis["high_conflict_risk"] = True
                break

        return analysis

    def get_branch_age_days(self, branch: str) -> int:
        """Get branch age in days since the branch's first unique commit."""
        from datetime import datetime

        upstream = self.develop_branch
        try:
            cmd = ["git", "rev-list", "--reverse", branch, "--not", upstream]
            result = self.run_command(cmd)
            lines = [l.strip() for l in result.stdout.splitlines() if l.strip()]  # noqa
            commit_hash = lines[0] if lines else None

            if not commit_hash:
                cmd = ["git", "rev-parse", f"{branch}"]
                result = self.run_command(cmd)
                commit_hash = result.stdout.strip()
                if not commit_hash:
                    return 0

            cmd = ["git", "show", "-s", "--format=%ci", commit_hash]
            result = self.run_command(cmd)
            commit_date_str = result.stdout.splitlines()[0].strip()
            first_date = datetime.strptime(commit_date_str.split()[0], "%Y-%m-%d")
            return (datetime.now() - first_date).days

        except (subprocess.CalledProcessError, ValueError, IndexError):
            return 0

    def should_sync_develop_branch(self, branch: str = None) -> tuple[bool, dict]:
        """Determine if should sync with develop branch before MR."""
        if branch is None:
            branch = self.working_branch

        if branch == self.develop_branch:
            return False, {"reason": "already_on_develop"}

        self.console.print(
            f"\n🔍 分析分支 {branch} 与 {self.develop_branch} 的差异...", style="cyan"
        )

        target_ahead, branch_ahead = self.get_commit_divergence(
            branch, self.develop_branch
        )

        changed_files = self.get_changed_files(branch, self.develop_branch)
        file_analysis = self.analyze_file_changes(changed_files)

        branch_age = self.get_branch_age_days(branch)

        should_sync = False
        reasons = []

        if target_ahead > self.divergence_threshold:
            should_sync = True
            reasons.append(
                f"divergence较大 ({target_ahead} > {self.divergence_threshold})"
            )

        if file_analysis["high_conflict_risk"]:
            should_sync = True
            reasons.append("涉及核心模块或大量同文件修改")

        if branch_age > self.long_lived_branch_days:
            should_sync = True
            reasons.append(
                f"长期分支 ({branch_age}天 > {self.long_lived_branch_days}天)"
            )

        if file_analysis["migration_files"] > 0:
            should_sync = True
            reasons.append("包含数据库迁移文件")

        analysis = {
            "target_ahead": target_ahead,
            "branch_ahead": branch_ahead,
            "changed_files_count": len(changed_files),
            "file_analysis": file_analysis,
            "branch_age_days": branch_age,
            "should_sync": should_sync,
            "reasons": reasons,
        }

        return should_sync, analysis

    def display_divergence_analysis(self, analysis: dict) -> None:
        """Display branch divergence analysis results."""
        self.console.print("\n📊 分支差异分析结果:", style="bold cyan")
        self.console.print("=" * 50, style="blue")

        self.console.print("📈 提交差异:", style="yellow")
        self.console.print(
            f"  • {self.develop_branch} 领先: {analysis['target_ahead']} 个提交"
        )
        self.console.print(f"  • 当前分支领先: {analysis['branch_ahead']} 个提交")

        file_analysis = analysis["file_analysis"]
        self.console.print("\n📁 文件改动:", style="yellow")
        self.console.print(f"  • 总计改动文件: {analysis['changed_files_count']}")
        self.console.print(f"  • 核心模块文件: {file_analysis['core_modules']}")
        self.console.print(f"  • 后端文件: {file_analysis['backend_files']}")
        self.console.print(f"  • 迁移文件: {file_analysis['migration_files']}")

        if file_analysis["directory_changes"]:
            self.console.print("\n📂 目录改动分布:", style="yellow")
            for dir_path, count in file_analysis["directory_changes"].items():
                if count > 3:
                    risk_indicator = (
                        "⚠️" if count > self.file_change_threshold else "✅"
                    )
                    self.console.print(f"  {risk_indicator} {dir_path}: {count} 个文件")

        self.console.print("\n📅 分支信息:", style="yellow")
        self.console.print(f"  • 分支存在时间: {analysis['branch_age_days']} 天")

        if analysis["should_sync"]:
            self.console.print(
                f"\n🔄 建议同步 {self.develop_branch} 分支:", style="bold red"
            )
            for reason in analysis["reasons"]:
                self.console.print(f"  • {reason}")
        else:
            self.console.print("\n✅ 可以直接提交 MR，无需同步", style="bold green")

        self.console.print("=" * 50, style="blue")

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

        self.run_command(["git", "add", "."])

        self.console.print("✅ 文件已暂存", style="green")
        return True

    async def generate_commit_message(self) -> str:
        """Generate commit message using LLM based on git changes."""
        self.console.print("\n🤖 正在分析代码变更并生成提交信息...", style="cyan")

        try:
            diff_result = self.run_command(["git", "diff", "--cached", "--stat"])
            detailed_diff = self.run_command(["git", "diff", "--cached"])

            files_result = self.run_command(["git", "diff", "--cached", "--name-only"])
            changed_files = (
                files_result.stdout.strip().split("\n")
                if files_result.stdout.strip()
                else []
            )

            context = f"""
代码变更统计：
{diff_result.stdout}

变更文件列表：
{chr(10).join(changed_files)}

详细变更内容：
{detailed_diff.stdout[:2000]}

请基于以上代码变更生成符合规范的Git提交信息。
"""

            result = await self.commit_agent.run(context)
            print(result.output)
            commit_msg = result.output.message

            self.console.print("\n🤖 AI 生成的提交信息:", style="cyan")
            panel = Panel(commit_msg, title="AI 生成", border_style="green")
            self.console.print(panel)

            return commit_msg

        except Exception as e:
            self.console.print(f"⚠️  AI 生成提交信息失败: {e}", style="yellow")
            self.console.print("回退到手动输入模式...", style="yellow")
            return self._fallback_commit_message()

    def _fallback_commit_message(self) -> str:
        """Fallback method for manual commit message input."""
        if self.language == "en":
            self.console.print("\n📝 Commit Message Guidelines:", style="cyan")
            self.console.print("Format: <type>(<scope>): <subject>")
            self.console.print("Types: feat, fix, refactor, docs, style, test, chore")
            self.console.print(
                "Example: feat(auth): add user authentication functionality"
            )

            while True:
                subject = input("\nEnter commit title: ").strip()
                if not subject:
                    self.console.print("❌ Commit title cannot be empty", style="red")
                    continue

                body = input(
                    "Enter detailed description (optional, press Enter to skip): "
                ).strip()

                commit_msg = subject
                if body:
                    commit_msg += f"\n\n{body}"

                self.console.print("\n📋 Commit Message Preview:", style="cyan")
                panel = Panel(commit_msg, title="Preview", border_style="yellow")
                self.console.print(panel)

                if self.confirm("Confirm using this commit message?"):
                    return commit_msg
                self.console.print("Please re-enter...", style="yellow")
        else:  # Default to Chinese
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

    def get_commit_message(self) -> str:
        """Get commit message (now using LLM generation)."""
        return asyncio.run(self.generate_commit_message())

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
            self.run_command(["git", "fetch", "origin"])

            self.run_command(["git", "checkout", self.develop_branch])
            self.run_command(["git", "pull", "origin", self.develop_branch])

            self.run_command(["git", "checkout", self.working_branch])

            try:
                self.run_command(["git", "rebase", self.develop_branch])
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


def commit(args) -> None:
    """Handle the commit command — git commit and push only."""
    workflow = GitWorkflow()

    workflow.console.print("🚀 开始 Git 提交和推送流程", style="bold green")
    workflow.console.print("=" * 60, style="blue")

    if not workflow.check_git_status():
        workflow.console.print("ℹ️  没有需要提交的更改", style="cyan")
        sys.exit(0)

    if not workflow.stage_changes():
        workflow.console.print("❌ 暂存失败，终止流程", style="red")
        sys.exit(1)

    commit_msg = workflow.get_commit_message()
    if not workflow.commit_changes(commit_msg):
        workflow.console.print("❌ 提交失败，终止流程", style="red")
        sys.exit(1)

    current_branch = workflow.get_current_branch()
    if not workflow.push_to_remote(current_branch):
        workflow.console.print("❌ 推送失败，终止流程", style="red")
        sys.exit(1)

    workflow.console.print("\n🎉 提交和推送完成!", style="bold green")

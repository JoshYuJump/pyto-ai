"""Git commit and merge request workflow implementation."""

import asyncio
import json
import os
import re
import subprocess
import sys
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path
from subprocess import CompletedProcess
from typing import Any, Dict, List, Optional, Tuple

import toml
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.text import Text


class CommitMessage(BaseModel):
    message: str = Field(description="Git commit message")


class MRContent(BaseModel):
    title: str = Field(description="Merge request title")
    description: str = Field(description="Merge request description")


class GitWorkflow:
    """Git workflow automation for commit and MR creation."""

    def __init__(self):
        self.console = Console(force_terminal=True, legacy_windows=False)
        self.config = self._load_config()
        self.settings = self._load_settings()

        # 从配置文件读取设置
        gitflow_config = self.config.get("gitflow", {})
        self.gitlab_host = gitflow_config.get("gitlab_host", "")
        self.gitlab_port = gitflow_config.get("gitlab_port", "")
        self.repo_name = gitflow_config.get("repo_name", "")
        self.develop_branch = gitflow_config.get("develop_branch", "develop")

        # 读取语言配置
        general_config = self.config.get("general", {})
        self.language = general_config.get("language", "zh")  # 默认中文

        # 记住当前工作分支
        self.working_branch = self.get_current_branch()

        # 分支差异检查的阈值配置
        self.divergence_threshold = 20  # A > 20 表示 divergence 较大
        self.file_change_threshold = 10  # 同目录下超过10个文件改动
        self.long_lived_branch_days = 14  # 长期分支阈值：2周

        # 设置 LLM 代理用于生成提交信息
        self._setup_commit_agent()

    def _get_settings_path(self) -> Path:
        """Get the path to the settings.json file."""
        home_dir = Path.home()
        pyto_dir = home_dir / ".pyto"
        pyto_dir.mkdir(exist_ok=True)
        return pyto_dir / "settings.json"

    def _load_settings(self) -> Dict[str, Any]:
        """Load LLM settings from ~/.pyto/settings.json."""
        settings_path = self._get_settings_path()
        self.console.print(f"Loading settings from: {settings_path}", style="cyan")

        if not settings_path.exists():
            self.console.print(
                "⚠️  未找到 ~/.pyto/settings.json 配置文件", style="yellow"
            )
            self.console.print("正在创建默认配置文件...", style="cyan")
            self._create_default_settings(settings_path)
            self.console.print(
                "✅ 已创建 ~/.pyto/settings.json 配置文件", style="green"
            )
            self.console.print("📝 请根据需要更新配置文件中的 LLM 设置", style="yellow")

        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                settings = json.load(f)

            # Store settings for provider configuration
            self.llm_settings = settings

            return settings
        except Exception as e:
            self.console.print(f"❌ 读取设置文件失败: {e}", style="red")
            self.console.print("使用默认设置", style="yellow")
            return {}

    def _create_default_settings(self, settings_path: Path) -> None:
        """Create default ~/.pyto/settings.json configuration file."""
        default_settings = {
            "env": {
                "ANTHROPIC_AUTH_TOKEN": "your-anthropic-token-here",
                "ANTHROPIC_BASE_URL": "your-anthropic-base-url-here",
            },
            "model": "minimax-m2.7",
        }

        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(default_settings, f, indent=2, ensure_ascii=False)

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
        """Setup commit message generation agent using settings."""
        # Get model from settings, default to gpt-4o-mini
        model_name: str = self.settings.get("model", "gpt-4o-mini")

        # Get environment settings
        env_settings = self.settings.get("env", {})

        # Anthropic provider
        api_key = env_settings.get("ANTHROPIC_AUTH_TOKEN")
        base_url = env_settings.get("ANTHROPIC_BASE_URL")

        if api_key:
            provider = AnthropicProvider(api_key=api_key, base_url=base_url)
        else:
            provider = None

        self.console.print(f"🤖 使用模型: {model_name}", style="cyan")
        model = AnthropicModel(model_name, provider=provider)
        # Create agent with provider if available

        self.commit_agent = Agent(
            model,
            output_type=CommitMessage,
            system_prompt=self._get_commit_prompt(),
        )

        self.mr_agent = Agent(
            model,
            output_type=MRContent,
            system_prompt=self._get_mr_prompt(),
        )

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
    ) -> Tuple[int, int]:
        """Get commit divergence between branches.

        Returns:
            Tuple[int, int]: (A, B) where A = target_branch commits ahead of branch,
                           B = branch commits ahead of target_branch
        """
        if target_branch is None:
            target_branch = self.develop_branch

        try:
            # Fetch latest changes first
            self.run_command(["git", "fetch", "origin"])

            # Get commit count divergence
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

    def get_changed_files(self, branch: str, target_branch: str = None) -> List[str]:
        """Get list of changed files between branches."""
        if target_branch is None:
            target_branch = self.develop_branch

        try:
            # Fetch latest changes first
            self.run_command(["git", "fetch", "origin"])

            cmd = [
                "git",
                "diff",
                "--name-only",
                f"origin/{target_branch}...origin/{branch}",
            ]
            result = self.run_command(cmd)

            files = [f.strip() for f in result.stdout.split("\n") if f.strip()]
            return files

        except subprocess.CalledProcessError:
            self.console.print("❌ 无法获取改动文件列表", style="red")
            return []

    def analyze_file_changes(self, files: List[str]) -> dict:
        """Analyze file changes to determine conflict probability."""
        analysis = {
            "total_files": len(files),
            "core_modules": 0,
            "backend_files": 0,
            "migration_files": 0,
            "directory_changes": {},
            "high_conflict_risk": False,
        }

        # Define patterns for core modules and high-risk files
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
            # Check for core modules
            for pattern in core_patterns:
                if re.search(pattern, file_path, re.IGNORECASE):
                    analysis["core_modules"] += 1
                    analysis["high_conflict_risk"] = True
                    break

            # Check for backend files
            for pattern in backend_patterns:
                if re.search(pattern, file_path):
                    analysis["backend_files"] += 1
                    break

            # Check for migration files
            for pattern in migration_patterns:
                if re.search(pattern, file_path, re.IGNORECASE):
                    analysis["migration_files"] += 1
                    analysis["high_conflict_risk"] = True
                    break

            # Track directory changes
            directory = Path(file_path).parent.as_posix()
            analysis["directory_changes"][directory] = (
                analysis["directory_changes"].get(directory, 0) + 1
            )

        # Check if any directory has too many changes
        for count in analysis["directory_changes"].values():
            if count > self.file_change_threshold:
                analysis["high_conflict_risk"] = True
                break

        return analysis

    def get_branch_age_days(self, branch: str) -> int:
        """Get branch age in days since first commit."""
        try:
            # Get the first commit date of the branch
            cmd = ["git", "log", "--reverse", "--format=%ci", f"origin/{branch}"]
            result = self.run_command(cmd)

            if result.stdout.strip():
                first_commit_date = result.stdout.split("\n")[0].strip()
                first_date = datetime.strptime(first_commit_date.split()[0], "%Y-%m-%d")
                age_days = (datetime.now() - first_date).days
                return age_days

            return 0

        except (subprocess.CalledProcessError, ValueError):
            return 0

    def should_sync_develop_branch(self, branch: str = None) -> Tuple[bool, dict]:
        """Determine if should sync with develop branch before MR.

        Returns:
            Tuple[bool, dict]: (should_sync, analysis_details)
        """
        if branch is None:
            branch = self.working_branch

        # Skip if on develop branch itself
        if branch == self.develop_branch:
            return False, {"reason": "already_on_develop"}

        self.console.print(
            f"\n🔍 分析分支 {branch} 与 {self.develop_branch} 的差异...", style="cyan"
        )

        # Get commit divergence
        target_ahead, branch_ahead = self.get_commit_divergence(
            branch, self.develop_branch
        )

        # Get changed files
        changed_files = self.get_changed_files(branch, self.develop_branch)
        file_analysis = self.analyze_file_changes(changed_files)

        # Get branch age
        branch_age = self.get_branch_age_days(branch)

        # Decision logic
        should_sync = False
        reasons = []

        # Check divergence threshold
        if target_ahead > self.divergence_threshold:
            should_sync = True
            reasons.append(
                f"divergence较大 ({target_ahead} > {self.divergence_threshold})"
            )

        # Check file change patterns
        if file_analysis["high_conflict_risk"]:
            should_sync = True
            reasons.append("涉及核心模块或大量同文件修改")

        # Check branch age
        if branch_age > self.long_lived_branch_days:
            should_sync = True
            reasons.append(
                f"长期分支 ({branch_age}天 > {self.long_lived_branch_days}天)"
            )

        # Check for migration files
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

        # Commit divergence
        self.console.print(f"📈 提交差异:", style="yellow")
        self.console.print(
            f"  • {self.develop_branch} 领先: {analysis['target_ahead']} 个提交"
        )
        self.console.print(f"  • 当前分支领先: {analysis['branch_ahead']} 个提交")

        # File changes
        file_analysis = analysis["file_analysis"]
        self.console.print(f"\n📁 文件改动:", style="yellow")
        self.console.print(f"  • 总计改动文件: {analysis['changed_files_count']}")
        self.console.print(f"  • 核心模块文件: {file_analysis['core_modules']}")
        self.console.print(f"  • 后端文件: {file_analysis['backend_files']}")
        self.console.print(f"  • 迁移文件: {file_analysis['migration_files']}")

        # Directory changes
        if file_analysis["directory_changes"]:
            self.console.print(f"\n📂 目录改动分布:", style="yellow")
            for dir_path, count in file_analysis["directory_changes"].items():
                if count > 3:  # Only show directories with significant changes
                    risk_indicator = (
                        "⚠️" if count > self.file_change_threshold else "✅"
                    )
                    self.console.print(f"  {risk_indicator} {dir_path}: {count} 个文件")

        # Branch age
        self.console.print(f"\n📅 分支信息:", style="yellow")
        self.console.print(f"  • 分支存在时间: {analysis['branch_age_days']} 天")

        # Recommendation
        if analysis["should_sync"]:
            self.console.print(
                f"\n🔄 建议同步 {self.develop_branch} 分支:", style="bold red"
            )
            for reason in analysis["reasons"]:
                self.console.print(f"  • {reason}")
        else:
            self.console.print(f"\n✅ 可以直接提交 MR，无需同步", style="bold green")

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

        # Let user specify files interactively
        self.run_command(["git", "add", "."])

        self.console.print("✅ 文件已暂存", style="green")
        return True

    async def generate_commit_message(self) -> str:
        """Generate commit message using LLM based on git changes."""
        self.console.print("\n🤖 正在分析代码变更并生成提交信息...", style="cyan")

        try:
            # Get git diff to analyze changes
            diff_result = self.run_command(["git", "diff", "--cached", "--stat"])
            detailed_diff = self.run_command(["git", "diff", "--cached"])

            # Get list of changed files
            files_result = self.run_command(["git", "diff", "--cached", "--name-only"])
            changed_files = (
                files_result.stdout.strip().split("\n")
                if files_result.stdout.strip()
                else []
            )

            # Prepare context for LLM
            context = f"""
代码变更统计：
{diff_result.stdout}

变更文件列表：
{chr(10).join(changed_files)}

详细变更内容：
{detailed_diff.stdout[:2000]}  # 限制长度避免token过多

请基于以上代码变更生成符合规范的Git提交信息。
"""

            # Generate commit message using LLM
            result = await self.commit_agent.run(context)
            print(result.output)
            commit_msg = result.output.message

            # Display generated message
            self.console.print("\n� AI 生成的提交信息:", style="cyan")
            panel = Panel(commit_msg, title="AI 生成", border_style="green")
            self.console.print(panel)

            return commit_msg
            # # Ask for user confirmation
            # if self.confirm("是否使用 AI 生成的提交信息？"):
            #     return commit_msg
            # else:
            #     return self._fallback_commit_message()

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

    async def generate_mr_content(self, branch: str) -> Tuple[str, str]:
        """Generate MR title and description using LLM based on branch changes and commit history."""
        self.console.print("\n🤖 正在分析分支变更并生成 MR 标题和描述...", style="cyan")

        try:
            # Get git diff between branches
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

            # Get list of changed files
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

            # Get detailed commit messages for context
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

                # Get detailed commit info
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

            # Prepare context for LLM
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
{detailed_diff.stdout[:2000]}  # 限制长度避免token过多

请基于以上分支变更信息同时生成简洁的标题和详细的描述。
"""

            # Generate MR content using LLM
            result = await self.mr_agent.run(context)
            mr_title = result.output.title
            mr_description = result.output.description

            # Display generated title and description
            self.console.print("\n🤖 AI 生成的 MR 标题:", style="cyan")
            title_panel = Panel(mr_title, title="标题", border_style="green")
            self.console.print(title_panel)

            self.console.print("\n🤖 AI 生成的 MR 描述:", style="cyan")
            desc_panel = Panel(mr_description, title="描述", border_style="green")
            self.console.print(desc_panel)

            return mr_title, mr_description
            # # Ask for user confirmation
            # if self.confirm("是否使用 AI 生成的 MR 标题和描述？"):
            #     return mr_title, mr_description
            # else:
            #     return self._fallback_mr_content(branch)

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
                # Get title
                title = input("\nEnter MR title: ").strip()
                if not title:
                    self.console.print("❌ MR title cannot be empty", style="red")
                    continue

                # Get description
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

                # Preview
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
                # Get title
                title = input("\n请输入 MR 标题: ").strip()
                if not title:
                    self.console.print("❌ MR 标题不能为空", style="red")
                    continue

                # Get description
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

                # Preview
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

            # Go back to working branch
            self.run_command(["git", "checkout", self.working_branch])

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
            # Generate MR title and description using LLM in one request
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

            # Extract MR number from output
            #
            self.console.print("MR result.stdout: %s" % result.stdout)
            mr_url = result.stdout
            # Auto-open browser
            try:
                webbrowser.open(mr_url)
                self.console.print(f"🌐 已自动打开 MR 页面: {mr_url}", style="green")
            except:  # noqa: E722
                self.console.print(f"📎 MR 链接: {mr_url}", style="cyan")
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

    # Step 4: Check branch divergence and decide on sync strategy
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
        workflow.console.print(f"✅ 跳过同步，直接提交 MR", style="green")

    # Step 5: Push to remote
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

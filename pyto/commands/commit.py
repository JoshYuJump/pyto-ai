"""Git commit and merge request workflow implementation."""

import os
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Optional


class GitWorkflow:
    """Git workflow automation for commit and MR creation."""
    
    def __init__(self):
        self.gitlab_host = "192.168.1.54"
        self.gitlab_port = "8008"
        self.repo_name = "yugu/yugu_yxpt"
        
    def run_command(self, cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
        """Run a command and return the result."""
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=check
            )
            return result
        except subprocess.CalledProcessError as e:
            print(f"❌ Error running command: {' '.join(cmd)}")
            print(f"STDERR: {e.stderr}")
            raise
    
    def confirm(self, message: str) -> bool:
        """Get user confirmation."""
        response = input(f"{message} [y/N]: ").strip().lower()
        return response in ['y', 'yes']
    
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
                print("❌ Git 检测到仓库所有权问题")
                print("请运行以下命令解决:")
                print(f"git config --global --add safe.directory '{os.getcwd()}'")
            else:
                print(f"❌ Git 状态检查失败: {e.stderr}")
            sys.exit(1)
    
    def code_review_checklist(self) -> bool:
        """Display code review checklist and get confirmation."""
        print("\n" + "="*60)
        print("📋 CODE REVIEW CHECKLIST")
        print("="*60)
        
        checklist = [
            ("代码质量检查", [
                "代码符合项目编码规范",
                "函数和变量命名清晰", 
                "注释充分且准确",
                "没有调试代码和 console.log",
                "没有硬编码的配置值"
            ]),
            ("功能完整性检查", [
                "功能实现符合需求",
                "边界条件已处理",
                "错误处理机制完善",
                "用户体验良好"
            ]),
            ("测试覆盖检查", [
                "单元测试已编写",
                "测试覆盖主要功能",
                "测试用例包含边界情况",
                "所有测试通过"
            ]),
            ("安全性检查", [
                "输入验证已实现",
                "权限控制正确",
                "敏感信息已保护",
                "SQL注入等安全问题已防范"
            ]),
            ("性能检查", [
                "数据库查询优化",
                "没有N+1查询问题",
                "缓存策略合理",
                "前端性能优化"
            ])
        ]
        
        for category, items in checklist:
            print(f"\n🔍 {category}:")
            for item in items:
                print(f"  □ {item}")
        
        print("\n" + "="*60)
        return self.confirm("请逐项检查上述清单，确认无误后继续")
    
    def stage_changes(self) -> bool:
        """Stage changes for commit."""
        print("\n📁 检查当前状态...")
        result = self.run_command(["git", "status"])
        print(result.stdout)
        
        if not self.confirm("是否要添加所有更改到暂存区？"):
            # Let user specify files interactively
            files_input = input("请输入要暂存的文件路径（用空格分隔）: ").strip()
            if files_input:
                files = files_input.split()
                for file_path in files:
                    self.run_command(["git", "add", file_path])
            else:
                print("❌ 未暂存任何文件")
                return False
        else:
            self.run_command(["git", "add", "."])
        
        print("✅ 文件已暂存")
        return True
    
    def get_commit_message(self) -> str:
        """Get commit message from user."""
        print("\n📝 提交信息规范:")
        print("格式: <type>(<scope>): <subject>")
        print("类型: feat, fix, refactor, docs, style, test, chore")
        print("示例: feat(auth): 添加用户认证功能")
        
        while True:
            subject = input("\n请输入提交标题: ").strip()
            if not subject:
                print("❌ 提交标题不能为空")
                continue
            
            body = input("请输入详细描述（可选，按回车跳过）: ").strip()
            
            commit_msg = subject
            if body:
                commit_msg += f"\n\n{body}"
            
            print(f"\n📋 提交信息预览:")
            print("-" * 40)
            print(commit_msg)
            print("-" * 40)
            
            if self.confirm("确认使用此提交信息？"):
                return commit_msg
            print("请重新输入...")
    
    def commit_changes(self, message: str) -> bool:
        """Commit staged changes."""
        try:
            self.run_command(["git", "commit", "-m", message])
            print("✅ 代码已提交")
            return True
        except subprocess.CalledProcessError:
            print("❌ 提交失败")
            return False
    
    def sync_prepare_branch(self) -> bool:
        """Sync with prepare branch."""
        print("\n🔄 同步 prepare 分支...")
        
        try:
            # Fetch latest changes
            self.run_command(["git", "fetch", "origin"])
            
            # Checkout and pull prepare branch
            self.run_command(["git", "checkout", "prepare"])
            self.run_command(["git", "pull", "origin", "prepare"])
            
            # Go back to feature branch
            current_branch = self.get_current_branch()
            self.run_command(["git", "checkout", current_branch])
            
            # Merge prepare into feature branch
            try:
                self.run_command(["git", "merge", "prepare"])
                print("✅ 已同步 prepare 分支")
                return True
            except subprocess.CalledProcessError:
                print("⚠️  合并冲突，请手动解决后继续")
                if not self.confirm("是否已解决冲突并继续？"):
                    return False
                self.run_command(["git", "add", "."])
                self.run_command(["git", "commit", "-m", "resolve: 合并 prepare 分支的更改"])
                return True
                
        except subprocess.CalledProcessError as e:
            print(f"❌ 同步失败: {e}")
            return False
    
    def push_to_remote(self, branch: str) -> bool:
        """Push branch to remote."""
        try:
            self.run_command(["git", "push", "origin", branch])
            print(f"✅ 已推送分支 {branch} 到远程")
            return True
        except subprocess.CalledProcessError:
            print(f"❌ 推送分支 {branch} 失败")
            return False
    
    def check_glab_auth(self) -> bool:
        """Check if glab is authenticated."""
        try:
            result = self.run_command(
                ["glab", "auth", "status", "--hostname", self.gitlab_host],
                check=False
            )
            return result.returncode == 0
        except FileNotFoundError:
            print("❌ 未找到 glab 命令，请先安装 GitLab CLI")
            return False
    
    def create_merge_request(self, branch: str) -> Optional[str]:
        """Create merge request and return MR URL."""
        if not self.check_glab_auth():
            print("🔐 请先登录 GitLab:")
            print(f"glab auth login -p http --hostname {self.gitlab_host}")
            if not self.confirm("登录完成后是否继续？"):
                return None
        
        try:
            # Create MR with prepare as target branch
            title = input("请输入 MR 标题: ").strip() or branch
            cmd = [
                "glab", "mr", "create",
                "--fill",
                "--repo", self.repo_name,
                "--target-branch", "prepare",
                "--source-branch", branch,
                "--title", title,
                "-y"
            ]
            
            result = self.run_command(cmd)
            
            # Extract MR number from output
            import re
            mr_match = re.search(r'!(\d+)', result.stdout)
            if mr_match:
                mr_number = mr_match.group(1)
                mr_url = f"http://{self.gitlab_host}:{self.gitlab_port}/{self.repo_name}/-/merge_requests/{mr_number}"
                
                # Auto-open browser
                try:
                    webbrowser.open(mr_url)
                    print(f"🌐 已自动打开 MR 页面: {mr_url}")
                except:
                    print(f"📎 MR 链接: {mr_url}")
                
                return f"[MR !{mr_number}: {title}]({mr_url})"
            
            print("⚠️  无法获取 MR 编号")
            return None
            
        except subprocess.CalledProcessError as e:
            print(f"❌ 创建 MR 失败: {e}")
            return None
    
    def cleanup(self, branch: str) -> None:
        """Cleanup after successful merge."""
        print(f"\n🧹 清理分支 {branch}...")
        
        try:
            # Switch to prepare branch
            self.run_command(["git", "checkout", "prepare"])
            self.run_command(["git", "pull", "origin", "prepare"])
            
            # Delete local branch
            self.run_command(["git", "branch", "-d", branch])
            
            # Delete remote branch
            self.run_command(["git", "push", "origin", "--delete", branch])
            
            print(f"✅ 已清理分支 {branch}")
        except subprocess.CalledProcessError as e:
            print(f"⚠️  清理失败: {e}")


def handle_commit_command(args) -> None:
    """Handle the commit command."""
    workflow = GitWorkflow()
    
    print("🚀 开始 Git 提交和 MR 创建流程")
    print("="*60)
    
    # Step 1: Code Review Checklist
    if not args.skip_review:
        if not workflow.code_review_checklist():
            print("❌ 代码审核未通过，终止流程")
            sys.exit(1)
    
    # Check if there are changes to commit
    if not workflow.check_git_status():
        print("ℹ️  没有需要提交的更改")
        sys.exit(0)
    
    # Step 2: Stage changes
    if not workflow.stage_changes():
        print("❌ 暂存失败，终止流程")
        sys.exit(1)
    
    # Step 3: Get commit message and commit
    commit_msg = workflow.get_commit_message()
    if not workflow.commit_changes(commit_msg):
        print("❌ 提交失败，终止流程")
        sys.exit(1)
    
    # Step 4: Sync with prepare branch
    if not workflow.sync_prepare_branch():
        print("❌ 同步失败，终止流程")
        sys.exit(1)
    
    # Step 5: Push to remote
    current_branch = workflow.get_current_branch()
    if not workflow.push_to_remote(current_branch):
        print("❌ 推送失败，终止流程")
        sys.exit(1)
    
    # Step 6: Create MR
    mr_link = workflow.create_merge_request(current_branch)
    if mr_link:
        print(f"\n✅ MR 创建成功!")
        print(f"📋 {mr_link}")
        print("\n📝 等待代码审查和合并...")
    else:
        print("❌ MR 创建失败")
        sys.exit(1)
    
    print("\n🎉 流程完成!")

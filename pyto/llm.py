"""Shared LLM settings and agent factory."""

import json
from pathlib import Path
from typing import Any, Dict, Type

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from rich.console import Console

console = Console(force_terminal=True, legacy_windows=False)


def get_settings_path() -> Path:
    """Get the path to the settings.json file."""
    home_dir = Path.home()
    pyto_dir = home_dir / ".pyto"
    pyto_dir.mkdir(exist_ok=True)
    return pyto_dir / "settings.json"


def create_default_settings(settings_path: Path) -> None:
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


def load_settings() -> Dict[str, Any]:
    """Load LLM settings from ~/.pyto/settings.json."""
    settings_path = get_settings_path()
    console.print(f"Loading settings from: {settings_path}", style="cyan")

    if not settings_path.exists():
        console.print("⚠️  未找到 ~/.pyto/settings.json 配置文件", style="yellow")
        console.print("正在创建默认配置文件...", style="cyan")
        create_default_settings(settings_path)
        console.print("✅ 已创建 ~/.pyto/settings.json 配置文件", style="green")
        console.print("📝 请根据需要更新配置文件中的 LLM 设置", style="yellow")

    try:
        with open(settings_path, "r", encoding="utf-8") as f:
            settings = json.load(f)
        return settings
    except Exception as e:
        console.print(f"❌ 读取设置文件失败: {e}", style="red")
        console.print("使用默认设置", style="yellow")
        return {}


def create_agent(
    output_type: Type[BaseModel],
    system_prompt: str,
    model_name: str | None = None,
) -> Agent:
    """Create a pydantic-ai Agent with settings from ~/.pyto/settings.json.

    Args:
        output_type: Pydantic model class for structured output.
        system_prompt: System prompt for the agent.
        model_name: Override model name. If None, reads from settings.
    """
    settings = load_settings()

    if model_name is None:
        model_name = settings.get("model", "gpt-4o-mini")

    env_settings = settings.get("env", {})
    api_key = env_settings.get("ANTHROPIC_AUTH_TOKEN")
    base_url = env_settings.get("ANTHROPIC_BASE_URL")

    if api_key:
        provider = AnthropicProvider(api_key=api_key, base_url=base_url)
    else:
        provider = None

    console.print(f"🤖 使用模型: {model_name}", style="cyan")
    model = AnthropicModel(model_name, provider=provider)

    return Agent(model, output_type=output_type, system_prompt=system_prompt)

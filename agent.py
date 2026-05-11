"""PyTo Code - Code Agent with Pydantic-AI."""

import os
import subprocess
from pathlib import Path

from dotenv import load_dotenv
from pydantic_ai import Agent, Tool
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.messages import ModelMessage

# Load .env file
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)


class AgentSession:
    """A session that maintains conversation history."""

    def __init__(self, model: str = None):
        self.model = model or get_model()
        self.api_key = get_api_key()
        self.agent = self._create_agent()
        self._message_history: list[ModelMessage] = []

    def _create_agent(self) -> Agent:
        """Create the underlying Pydantic-AI agent."""
        base_url = get_base_url()
        if base_url:
            provider = AnthropicProvider(api_key=self.api_key, base_url=base_url)
        else:
            provider = AnthropicProvider(api_key=self.api_key)

        anthropic_model = AnthropicModel(self.model, provider=provider)
        return Agent(
            anthropic_model,
            tools=[Tool(run_code), Tool(write_file)],
        )

    async def run(self, prompt: str) -> str:
        """Run with conversation history."""
        result = await self.agent.run(
            prompt,
            message_history=self._message_history,
        )
        # Update message history with new messages
        self._message_history = list(result._state.message_history)
        return result.output


# Global session (for backward compatibility)
_global_session: AgentSession | None = None


def get_model() -> str:
    """Get the model from environment variables."""
    # Claude Code style env vars
    if os.environ.get("ANTHROPIC_DEFAULT_OPUS_MODEL"):
        return os.environ.get("ANTHROPIC_DEFAULT_OPUS_MODEL")
    if os.environ.get("ANTHROPIC_DEFAULT_SONNET_MODEL"):
        return os.environ.get("ANTHROPIC_DEFAULT_SONNET_MODEL")
    if os.environ.get("ANTHROPIC_DEFAULT_HAIKU_MODEL"):
        return os.environ.get("ANTHROPIC_DEFAULT_HAIKU_MODEL")
    return os.environ.get("PYTO_MODEL", "claude-sonnet-4-20250514")


def get_api_key() -> str:
    """Get the API key from environment variables."""
    # Claude Code style env var
    return os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get("ANTHROPIC_API_KEY")


def get_base_url() -> str:
    """Get the base URL from environment variables."""
    return os.environ.get("ANTHROPIC_BASE_URL")


def run_code(code: str) -> str:
    """Execute Python code and return the output."""
    result = subprocess.run(
        ["python", "-c", code],
        capture_output=True,
        text=True,
        timeout=30,
    )
    output = result.stdout
    if result.stderr:
        output += f"\nSTDERR: {result.stderr}"
    if not output:
        output = "(no output)"
    return output


def write_file(path: str, content: str) -> str:
    """Write content to a file at the specified path.

    Args:
        path: The file path to write to
        content: The content to write

    Returns:
        Success message or error
    """
    try:
        file_path = Path(path)
        # Create parent directories if they don't exist
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return f"Successfully wrote to {path}"
    except Exception as e:
        return f"Error writing to {path}: {e}"


def create_session(model: str = None) -> AgentSession:
    """Create a new agent session with conversation history."""
    return AgentSession(model)


def create_agent(model: str = None) -> Agent:
    """Create a PyTo Code agent (for backward compatibility)."""
    model = model or get_model()
    api_key = get_api_key()

    # Build provider with optional base_url
    base_url = get_base_url()
    if base_url:
        provider = AnthropicProvider(api_key=api_key, base_url=base_url)
    else:
        provider = AnthropicProvider(api_key=api_key)

    anthropic_model = AnthropicModel(model, provider=provider)
    agent = Agent(
        anthropic_model,
        tools=[Tool(run_code), Tool(write_file)],
    )
    return agent


async def run(prompt: str, model: str = None, session: AgentSession = None) -> str:
    """Run the agent with a prompt and return the result.

    If session is provided, conversation history is maintained.
    Otherwise, a new session is created (for backward compatibility).
    """
    if session is not None:
        return await session.run(prompt)

    # Fallback: create agent without history
    agent = create_agent(model)
    result = await agent.run(prompt)
    return result.output

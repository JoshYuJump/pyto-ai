# PyTo Code

A lightweight, extensible Python-first Code Agent framework for code generation, execution, and tooling with LLMs.

PyTo Code automates your Git workflow by using LLMs to generate commit messages and merge request descriptions. It integrates with GitLab via `glab` CLI and supports bilingual (Chinese/English) interfaces.

## Features

- **AI-powered commit messages** — Generates conventional commit messages from your staged diff
- **AI-powered merge requests** — Creates structured MR titles and descriptions with background, changes, and impact sections
- **Branch sync analysis** — Detects divergence from the target branch and recommends rebase strategies
- **GitLab integration** — Creates MRs and opens them in your browser via `glab`
- **Bilingual support** — Chinese (`zh`) and English (`en`) prompts and UI
- **Fallback to manual input** — If LLM generation fails, prompts for manual input

## Installation

```bash
# Clone the repository
git clone https://github.com/JoshYuJump/pyto-ai.git
cd pyto-ai

# Install with uv
uv sync
```

## Configuration

### 1. LLM Settings

Create `~/.pyto/settings.json` (auto-created on first run with defaults):

```json
{
  "env": {
    "ANTHROPIC_AUTH_TOKEN": "your-api-key-here",
    "ANTHROPIC_BASE_URL": "https://api.anthropic.com"
  },
  "model": "claude-sonnet-4-20250514"
}
```

PyTo Code uses the Anthropic API via Pydantic AI. You can point `ANTHROPIC_BASE_URL` to any Anthropic-compatible endpoint (e.g., Aliyun Dashscope, AWS Bedrock).

### 2. Project Configuration

Create a `pyto.toml` in your project root:

```toml
[general]
language = "en"  # "en" for English, "zh" for Chinese

[gitflow]
gitlab_host = "gitlab.example.com"
gitlab_port = "443"
repo_name = "group/project"
develop_branch = "main"
```

### 3. GitLab CLI

For the `submit` command, install and authenticate [glab](https://gitlab.com/gitlab-org/cli):

```bash
glab auth login
```

## Usage

### Commit

Stage changes, generate a commit message with AI, and push:

```bash
pyto commit
```

Skip the confirmation prompt:

```bash
pyto commit --skip-review
```

### Submit

Commit, push, and create a GitLab merge request:

```bash
pyto submit
```

Skip the confirmation prompt:

```bash
pyto submit --skip-review
```

The submit workflow will:
1. Check for uncommitted changes
2. Stage and commit with an AI-generated message
3. Analyze branch divergence from the target branch
4. Optionally sync/rebase with the target branch
5. Push to remote
6. Generate MR title and description with AI
7. Create the MR and open it in your browser

## Architecture

```
pyto/
├── __init__.py          # Package version
├── main.py              # CLI entry point (argparse)
├── llm.py               # LLM settings & Pydantic AI agent factory
└── commands/
    ├── __init__.py
    ├── commit.py         # GitWorkflow — commit & push
    └── submit.py         # SubmitWorkflow — commit, push & MR
```

The framework uses [Pydantic AI](https://ai.pydantic.dev/) for structured LLM interactions. Each command creates a typed agent with a Pydantic output model (`CommitMessage`, `MRContent`) to ensure responses conform to the expected schema.

## Development

```bash
# Install dev dependencies
uv sync --group dev

# Run tests
uv run pytest

# Lint
uv run ruff check .
```

## License

[Apache License 2.0](LICENSE)

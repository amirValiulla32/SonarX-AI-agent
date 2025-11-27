# Blockchain AI Monitoring Tool

An AI-powered monitoring agent that tracks Ethereum (go-ethereum) releases and automatically alerts you via Slack when breaking changes are detected.

## Current Features

- Monitors the ethereum/go-ethereum repository for new releases
- Uses Claude AI to intelligently analyze release notes for breaking changes
- Sends formatted alerts to Slack with severity levels and impact analysis
- Tracks seen releases to avoid duplicate notifications
- Runs continuously with configurable check intervals

## Breaking Change Detection

The agent classifies releases into three categories:

### Breaking (High Severity)
- Changes to block structure or transaction format
- Modifications to RPC endpoints
- Consensus rule changes
- Hard forks or network upgrades
- Database format changes
- API breaking changes

### Potentially Breaking (Medium Severity)
- Major version bumps
- Feature deprecations
- Configuration changes
- Significant performance changes

### Informational (Low Severity)
- Bug fixes
- Minor updates
- Security patches
- Documentation updates

## Setup Instructions

### 1. Clone and Set Up Environment

```bash
# Navigate to project directory
cd /path/to/sonarx-agent

# Create virtual environment
python3 -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate
# On Windows:
# venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment Variables

```bash
# Copy the example env file
cp .env.example .env

# Edit .env and add your credentials
nano .env
```

### 4. Test Your Setup

Before running the agent, verify everything works:

```bash
python test_setup.py
```

This will:
- Test GitHub API connection
- Fetch a real release and analyze it with Claude

If all tests pass, you're ready to go!

## Usage

### Run the code

Start the monitoring agent:

```bash
python agent.py
```

## How It Works
1. **Fetch**: Uses PyGithub to fetch the latest 5 releases from ethereum/go-ethereum
2. **Track**: Checks `seen_releases.json` to identify new releases
3. **Analyze**: Sends release notes to Claude API for intelligent analysis
4. **Alert**: Posts formatted Slack message with analysis results
5. **Persist**: Saves release ID to avoid duplicate notifications
6. **Loop**: Waits for configured interval and repeats

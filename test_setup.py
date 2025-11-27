#!/usr/bin/env python3
"""
Test script to verify API credentials and basic functionality.
Run this before starting the main agent to ensure everything is configured correctly.
"""

import os
import sys
from dotenv import load_dotenv
from github import Github, GithubException
from anthropic import Anthropic

# Slack is optional
try:
    from slack_sdk.webhook import WebhookClient
    SLACK_AVAILABLE = True
except ImportError:
    SLACK_AVAILABLE = False

# Load environment variables
load_dotenv()

# Configuration
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")
REPO_NAME = "ethereum/go-ethereum"


def print_section(title):
    """Print a formatted section header."""
    print(f"\n{'='*60}")
    print(f" {title}")
    print(f"{'='*60}")


def test_github_connection():
    """Test GitHub API connection and fetch one release."""
    print_section("Testing GitHub API Connection")

    if not GITHUB_TOKEN:
        print("ERROR: GITHUB_TOKEN not found in .env file")
        return False

    try:
        print(f"Connecting to GitHub...")
        github = Github(GITHUB_TOKEN)

        # Test authentication
        user = github.get_user()
        print(f"Authenticated as: {user.login}")

        # Fetch repository
        print(f"Fetching repository: {REPO_NAME}")
        repo = github.get_repo(REPO_NAME)
        print(f"Repository: {repo.full_name}")
        print(f"Stars: {repo.stargazers_count}")

        # Fetch latest release
        print(f"\nFetching latest release...")
        releases = repo.get_releases()
        latest = releases[0]

        print(f"\nLatest Release:")
        print(f"  Title: {latest.title or latest.tag_name}")
        print(f"  Published: {latest.published_at}")
        print(f"  URL: {latest.html_url}")

        print("\nGitHub API: OK")
        return latest

    except GithubException as e:
        print(f"\nERROR: GitHub API failed")
        print(f"Status: {e.status}")
        print(f"Message: {e.data.get('message', str(e))}")
        return False
    except Exception as e:
        print(f"\nERROR: {e}")
        return False


def test_claude_analysis(release):
    """Test Claude API by analyzing a release."""
    print_section("Testing Claude API and Release Analysis")

    if not ANTHROPIC_API_KEY:
        print("ERROR: ANTHROPIC_API_KEY not found in .env file")
        return False

    if not release:
        print("ERROR: No release to analyze (GitHub test failed)")
        return False

    try:
        print(f"Initializing Anthropic client...")
        client = Anthropic(api_key=ANTHROPIC_API_KEY)

        release_title = release.title or release.tag_name
        release_body = release.body or "No release notes provided"

        # Truncate body if too long for test
        if len(release_body) > 2000:
            release_body = release_body[:2000] + "...[truncated for test]"

        print(f"Analyzing release: {release_title}")
        print(f"Release notes length: {len(release_body)} characters")

        prompt = f"""Analyze this Ethereum go-ethereum release for breaking changes.

Release Title: {release_title}

Release Notes:
{release_body}

Return a JSON object with this structure:
{{
  "is_breaking": true/false,
  "severity": "high"/"medium"/"low",
  "reason": "Brief explanation",
  "affected_components": ["list", "of", "components"]
}}

Return ONLY the JSON object."""

        print(f"\nSending request to Claude API...")
        response = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=1024,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        content = response.content[0].text.strip()

        # Remove markdown code blocks if present
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]

        import json
        analysis = json.loads(content.strip())

        print(f"\nAnalysis Result:")
        print(f"  Breaking Change: {analysis['is_breaking']}")
        print(f"  Severity: {analysis['severity']}")
        print(f"  Reason: {analysis['reason']}")
        print(f"  Affected Components: {', '.join(analysis['affected_components'])}")

        print("\nClaude API: OK")
        return analysis

    except Exception as e:
        print(f"\nERROR: Claude API failed")
        print(f"Error: {e}")
        return False


def test_slack_notification(release, analysis):
    """Test Slack webhook by sending a test message."""
    print_section("Testing Slack Webhook")

    if not SLACK_WEBHOOK_URL:
        print("SKIPPED: SLACK_WEBHOOK_URL not configured")
        print("The agent will use console output for notifications.")
        return None  # None indicates skipped, not failed

    if not SLACK_AVAILABLE:
        print("SKIPPED: slack-sdk not installed")
        print("Install with: pip install slack-sdk")
        print("The agent will use console output for notifications.")
        return None

    if not release or not analysis:
        print("ERROR: Cannot test Slack (previous tests failed)")
        return False

    try:
        print(f"Initializing Slack webhook client...")
        webhook = WebhookClient(SLACK_WEBHOOK_URL)

        release_title = release.title or release.tag_name
        release_url = release.html_url

        is_breaking = analysis.get("is_breaking", False)
        severity = analysis.get("severity", "low").upper()
        reason = analysis.get("reason", "No reason provided")
        components = analysis.get("affected_components", [])

        emoji = ":test_tube:"
        status = "TEST MESSAGE"

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} TEST: Ethereum Release Monitor"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"This is a test message from your Ethereum Release Monitor setup."
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Test Release:*\n{release_title}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Analysis Result:*\n{'Breaking' if is_breaking else 'Non-Breaking'} ({severity})"
                    }
                ]
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Reason:*\n{reason}"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Affected Components:*\n{', '.join(components)}"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"<{release_url}|View Release Notes>"
                }
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "If you see this message, your Slack integration is working correctly!"
                    }
                ]
            }
        ]

        print(f"Sending test message to Slack...")
        response = webhook.send(
            text=f"TEST: Ethereum Release Monitor - {release_title}",
            blocks=blocks
        )

        if response.status_code == 200:
            print(f"\nTest message sent successfully!")
            print(f"Check your Slack channel to verify you received it.")
            print("\nSlack Webhook: OK")
            return True
        else:
            print(f"\nERROR: Slack webhook failed")
            print(f"Status: {response.status_code}")
            print(f"Response: {response.body}")
            return False

    except Exception as e:
        print(f"\nERROR: Slack webhook failed")
        print(f"Error: {e}")
        return False


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print(" Ethereum Release Monitor - Setup Test")
    print("="*60)

    results = {
        "github": False,
        "claude": False,
        "slack": False
    }

    # Test 1: GitHub API
    release = test_github_connection()
    results["github"] = bool(release)

    # Test 2: Claude API
    if release:
        analysis = test_claude_analysis(release)
        results["claude"] = bool(analysis)
    else:
        analysis = None
        print_section("Testing Claude API and Release Analysis")
        print("SKIPPED: GitHub test failed")

    # Test 3: Slack Webhook
    if release and analysis:
        slack_result = test_slack_notification(release, analysis)
        results["slack"] = slack_result
    else:
        print_section("Testing Slack Webhook")
        print("SKIPPED: Previous tests failed")
        results["slack"] = None

    # Summary
    print_section("Test Summary")
    print(f"GitHub API:       {'PASS' if results['github'] else 'FAIL'}")
    print(f"Claude API:       {'PASS' if results['claude'] else 'FAIL'}")

    # Slack can be PASS, FAIL, or SKIPPED
    if results['slack'] is None:
        slack_status = "SKIPPED (optional)"
    elif results['slack']:
        slack_status = "PASS"
    else:
        slack_status = "FAIL"
    print(f"Slack Webhook:    {slack_status}")

    # Consider tests passed if required tests (GitHub, Claude) passed
    # Slack is optional
    required_tests_passed = results['github'] and results['claude']
    all_tests_passed = required_tests_passed and results['slack']

    if all_tests_passed:
        print("\n All tests passed! You're ready to run the agent.")
        print(f"\nRun: python agent.py")
        sys.exit(0)
    elif required_tests_passed:
        print("\n Required tests passed! You can run the agent.")
        print("   Notifications will be sent to console (Slack not configured)")
        print(f"\nRun: python agent.py")
        sys.exit(0)
    else:
        print("\n Some required tests failed. Please check your configuration.")
        print(f"\nMake sure you've set up your .env file with valid credentials.")
        sys.exit(1)


if __name__ == "__main__":
    main()

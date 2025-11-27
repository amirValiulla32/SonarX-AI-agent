#!/usr/bin/env python3
"""
Ethereum Blockchain Upgrade Monitoring Agent
Monitors ethereum/go-ethereum releases and alerts on breaking changes via Slack.
"""

import os
import json
import time
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from github import Github, GithubException
from anthropic import Anthropic
from dotenv import load_dotenv

# Slack is optional - only import if needed
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
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "600"))  # Default 10 minutes

REPO_NAME = "ethereum/go-ethereum"
SEEN_RELEASES_FILE = "seen_releases.json"


class ReleaseAnalyzer:
    """Analyzes Ethereum releases for breaking changes using Claude."""

    def __init__(self, api_key: str):
        try:
            self.client = Anthropic(api_key=api_key)
        except Exception as e:
            raise ValueError(f"Failed to initialize Anthropic client: {e}. Check your API key format.")

    def analyze_release(self, release_title: str, release_body: str) -> Dict:
        """
        Analyze a release for breaking changes.

        Returns:
            Dict with keys: is_breaking, severity, reason, affected_components
        """
        prompt = f"""Analyze this Ethereum go-ethereum release for breaking changes.

Release Title: {release_title}

Release Notes:
{release_body}

Classify this release based on these criteria:

BREAKING CHANGES (is_breaking=true, severity=high):
- Changes to block structure or transaction format
- Changes to RPC endpoints (removed/modified endpoints)
- Consensus rule changes
- Hard forks or network upgrades
- Database format changes requiring migration
- API breaking changes

POTENTIALLY BREAKING (is_breaking=true, severity=medium):
- Major version bumps
- Deprecated features that still work but will be removed
- Configuration changes that may affect existing setups
- Performance changes that significantly alter behavior

INFORMATIONAL (is_breaking=false, severity=low):
- Bug fixes
- Minor updates
- Security patches that don't change APIs
- Documentation updates

Return your analysis as a JSON object with this exact structure:
{{
  "is_breaking": true/false,
  "severity": "high"/"medium"/"low",
  "reason": "Brief explanation of why this is/isn't breaking",
  "affected_components": ["list", "of", "affected", "components"]
}}

Return ONLY the JSON object, no other text."""

        try:
            response = self.client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=1024,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            # Parse the response
            content = response.content[0].text.strip()

            # Remove markdown code blocks if present
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]

            analysis = json.loads(content.strip())

            # Validate required fields
            required_fields = ["is_breaking", "severity", "reason", "affected_components"]
            if not all(field in analysis for field in required_fields):
                raise ValueError(f"Missing required fields in analysis response")

            return analysis

        except Exception as e:
            print(f"Error analyzing release with Claude: {e}")
            # Return a safe default
            return {
                "is_breaking": False,
                "severity": "low",
                "reason": f"Analysis failed: {str(e)}",
                "affected_components": ["unknown"]
            }


class ConsoleNotifier:
    """Prints notifications to console (used when Slack is not configured)."""

    def send_alert(self, release_title: str, release_url: str, analysis: Dict) -> bool:
        """
        Print a formatted alert to console.

        Args:
            release_title: The release title/version
            release_url: Link to the release
            analysis: Analysis dict from ReleaseAnalyzer

        Returns:
            Always True (console output doesn't fail)
        """
        is_breaking = analysis.get("is_breaking", False)
        severity = analysis.get("severity", "low").upper()
        reason = analysis.get("reason", "No reason provided")
        components = analysis.get("affected_components", [])

        # Determine emoji based on breaking status
        if is_breaking:
            emoji = "⚠️ " if severity == "HIGH" else "🔶"
            status = "BREAKING CHANGE DETECTED"
        else:
            emoji = "ℹ️ "
            status = "Informational Update"

        # Print formatted alert
        print("\n" + "="*60)
        print(f"{emoji} ETHEREUM RELEASE ALERT")
        print("="*60)
        print(f"Release: {release_title}")
        print(f"Status: {status}")
        print(f"Severity: {severity}")
        print(f"\nWhy it matters:")
        print(f"  {reason}")
        if components:
            print(f"\nAffected Components:")
            print(f"  {', '.join(components)}")
        print(f"\nRelease Notes:")
        print(f"  {release_url}")
        print("="*60 + "\n")

        return True


class SlackNotifier:
    """Sends notifications to Slack."""

    def __init__(self, webhook_url: str):
        self.webhook = WebhookClient(webhook_url)

    def send_alert(self, release_title: str, release_url: str, analysis: Dict) -> bool:
        """
        Send a formatted alert to Slack.

        Args:
            release_title: The release title/version
            release_url: Link to the release
            analysis: Analysis dict from ReleaseAnalyzer

        Returns:
            True if successful, False otherwise
        """
        is_breaking = analysis.get("is_breaking", False)
        severity = analysis.get("severity", "low").upper()
        reason = analysis.get("reason", "No reason provided")
        components = analysis.get("affected_components", [])

        # Determine emoji and color based on breaking status
        if is_breaking:
            emoji = ":warning:" if severity == "HIGH" else ":large_orange_diamond:"
            color = "#ff0000" if severity == "HIGH" else "#ff9900"
            status = "BREAKING CHANGE DETECTED"
        else:
            emoji = ":information_source:"
            color = "#36a64f"
            status = "Informational Update"

        # Build the message
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} Ethereum Release: {release_title}"
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Status:*\n{status}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Severity:*\n{severity}"
                    }
                ]
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Why it matters:*\n{reason}"
                }
            }
        ]

        if components:
            components_text = ", ".join(components)
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Affected Components:*\n{components_text}"
                }
            })

        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"<{release_url}|View Release Notes>"
            }
        })

        try:
            response = self.webhook.send(
                text=f"New Ethereum Release: {release_title}",
                blocks=blocks
            )

            if response.status_code == 200:
                print(f"Slack notification sent successfully for {release_title}")
                return True
            else:
                print(f"Slack notification failed: {response.status_code} - {response.body}")
                return False

        except Exception as e:
            print(f"Error sending Slack notification: {e}")
            return False


class ReleaseTracker:
    """Tracks seen releases to avoid duplicates."""

    def __init__(self, file_path: str = SEEN_RELEASES_FILE):
        self.file_path = file_path
        self.seen_releases = self._load_seen_releases()

    def _load_seen_releases(self) -> set:
        """Load seen releases from JSON file."""
        if Path(self.file_path).exists():
            try:
                with open(self.file_path, 'r') as f:
                    data = json.load(f)
                    return set(data.get("releases", []))
            except Exception as e:
                print(f"Error loading seen releases: {e}")
                return set()
        return set()

    def _save_seen_releases(self):
        """Save seen releases to JSON file."""
        try:
            with open(self.file_path, 'w') as f:
                json.dump({
                    "releases": list(self.seen_releases),
                    "last_updated": datetime.now().isoformat()
                }, f, indent=2)
        except Exception as e:
            print(f"Error saving seen releases: {e}")

    def is_new_release(self, release_id: str) -> bool:
        """Check if a release is new (not seen before)."""
        return release_id not in self.seen_releases

    def mark_as_seen(self, release_id: str):
        """Mark a release as seen."""
        self.seen_releases.add(release_id)
        self._save_seen_releases()


class EthereumReleaseMonitor:
    """Main monitoring agent."""

    def __init__(self):
        # Validate required environment variables
        if not GITHUB_TOKEN:
            raise ValueError("GITHUB_TOKEN not set in environment")
        if not ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY not set in environment")

        self.github = Github(GITHUB_TOKEN)
        self.analyzer = ReleaseAnalyzer(ANTHROPIC_API_KEY)

        # Use Slack if configured and available, otherwise use console output
        if SLACK_WEBHOOK_URL and SLACK_AVAILABLE:
            self.notifier = SlackNotifier(SLACK_WEBHOOK_URL)
            notification_mode = "Slack"
        else:
            self.notifier = ConsoleNotifier()
            notification_mode = "Console"
            if not SLACK_WEBHOOK_URL:
                print("ℹ️  SLACK_WEBHOOK_URL not configured - using console output")
            elif not SLACK_AVAILABLE:
                print("ℹ️  slack-sdk not installed - using console output")

        self.tracker = ReleaseTracker()

        print(f"Initialized Ethereum Release Monitor for {REPO_NAME}")
        print(f"Notification mode: {notification_mode}")

    def fetch_latest_releases(self, limit: int = 5) -> List:
        """Fetch the latest releases from the repository."""
        try:
            repo = self.github.get_repo(REPO_NAME)
            releases = repo.get_releases()
            return list(releases[:limit])
        except GithubException as e:
            print(f"Error fetching releases from GitHub: {e}")
            return []

    def process_release(self, release):
        """Process a single release."""
        release_id = str(release.id)
        release_title = release.title or release.tag_name
        release_body = release.body or "No release notes provided"
        release_url = release.html_url

        print(f"\n{'='*60}")
        print(f"Processing: {release_title}")
        print(f"{'='*60}")

        # Check if already seen
        if not self.tracker.is_new_release(release_id):
            print(f"Already processed, skipping.")
            return

        # Analyze the release
        print(f"Analyzing release with Claude...")
        analysis = self.analyzer.analyze_release(release_title, release_body)

        print(f"Analysis result:")
        print(f"  Breaking: {analysis['is_breaking']}")
        print(f"  Severity: {analysis['severity']}")
        print(f"  Reason: {analysis['reason']}")
        print(f"  Components: {', '.join(analysis['affected_components'])}")

        # Send notification
        print(f"Sending notification...")
        success = self.notifier.send_alert(release_title, release_url, analysis)

        if success:
            # Mark as seen only if notification succeeded
            self.tracker.mark_as_seen(release_id)
            print(f"Release processed successfully!")
        else:
            print(f"Failed to send notification, will retry next time")

    def run_once(self):
        """Run a single check cycle."""
        print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Checking for new releases...")

        releases = self.fetch_latest_releases()

        if not releases:
            print("No releases found or error fetching releases")
            return

        print(f"Found {len(releases)} recent releases")

        # Process releases in reverse order (oldest first)
        for release in reversed(releases):
            self.process_release(release)

    def run_forever(self):
        """Run the monitor continuously."""
        print(f"Starting continuous monitoring (checking every {CHECK_INTERVAL} seconds)")
        print(f"Press Ctrl+C to stop\n")

        try:
            while True:
                self.run_once()
                print(f"\nSleeping for {CHECK_INTERVAL} seconds...")
                time.sleep(CHECK_INTERVAL)
        except KeyboardInterrupt:
            print("\n\nMonitoring stopped by user")
            sys.exit(0)


def main():
    """Main entry point."""
    try:
        monitor = EthereumReleaseMonitor()
        monitor.run_forever()
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

"""Raw Claude session transcripts remain local, like events.jsonl."""

import subprocess
from pathlib import Path


def test_claude_session_transcripts_are_ignored_and_untracked():
    repo = Path(__file__).resolve().parents[2]
    transcript = "evals/airflow/results/campaign/runs/case/model/run-1/attempt-0/session.jsonl"
    ignored = subprocess.run(["git", "check-ignore", "--no-index", "-q", transcript], cwd=repo)
    assert ignored.returncode == 0
    tracked = subprocess.check_output(["git", "ls-files", "--", "*session.jsonl"], cwd=repo, text=True)
    assert not tracked.strip(), tracked

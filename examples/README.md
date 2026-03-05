# Examples

Three real-world scenarios with public data. Upload the CSV, paste the prompt, and run.

## GitHub PR Checks

**CSV:** `github_checks.csv` | **Task:** `tasks/github-checks.yaml`

> For each PR URL, collect the PR title, author, merge status, list of approvers, CI check results (passed/failed/pending counts), and any linked Jira or issue tickets. Take screenshots of the PR page and the checks tab.

Tests navigation across PR tabs, text extraction, and screenshot capture.

## Wikipedia Citation Verification

**CSV:** `wikipedia_citations.csv` | **Task:** `tasks/wikipedia-citations.yaml`

> For each Wikipedia article, find the oldest cited source in the References section. Record the citation year, the claim it supports, and the source URL. Check if the source is still alive. If it's dead, try the Wayback Machine. Rate whether the claim is accurately supported by the source.

Tests deep page scrolling, external link following, and multi-step verification logic.

## Code Recency

**CSV:** `code_recency.csv` | **Task:** `tasks/code-recency.yaml`

> For each repository, find the file matching the code_string_hash identifier, check the git blame to find when it was last changed, and assess whether the change is materially significant for audit purposes (e.g. logic changes vs. renames). Check if it was modified within the last 90 days.

Tests GitHub code search/blame navigation, date parsing, and materiality assessment.

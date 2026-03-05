#!/usr/bin/env python3
"""Diagnostic script: dump GitHub PR DOM structure for selector discovery.

Usage:
    python tests/manual/dump_github_dom.py <PR_URL> [--headful]

Example:
    python tests/manual/dump_github_dom.py https://github.com/facebook/react/pull/25000
    python tests/manual/dump_github_dom.py https://github.com/facebook/react/pull/25000 --headful

Outputs JSON with selector candidates for each extraction target.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys


async def dump_pr_dom(url: str, headful: bool = False) -> dict:
    from playwright.async_api import async_playwright

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=not headful)
    page = await browser.new_page()

    print(f"Opening {url} ...", file=sys.stderr)
    await page.goto(url, wait_until="networkidle")
    await page.wait_for_timeout(2000)  # extra settle time for React hydration

    results = {}

    # ── Title area ──────────────────────────────────────────────────
    results["title"] = await page.evaluate("""() => {
        const out = {};
        // Primary: bdi.js-issue-title
        const bdi = document.querySelector('bdi.js-issue-title');
        out.bdi_js_issue_title = bdi ? bdi.textContent.trim() : null;

        // h1 text
        const h1 = document.querySelector('h1.gh-header-title');
        out.h1_gh_header_title = h1 ? h1.textContent.trim() : null;

        // page title
        out.page_title = document.title;

        // Any h1
        const anyH1 = document.querySelector('h1');
        out.first_h1 = anyH1 ? anyH1.innerHTML.substring(0, 500) : null;

        return out;
    }""")

    # ── PR number ───────────────────────────────────────────────────
    results["pr_number"] = await page.evaluate("""() => {
        const out = {};
        out.from_url = window.location.pathname.match(/\\/pull\\/(\\d+)/)?.[1] || null;

        // .gh-header-title .f1-light
        const numSpan = document.querySelector('.gh-header-title .f1-light');
        out.f1_light = numSpan ? numSpan.textContent.trim() : null;

        return out;
    }""")

    # ── Merge status ────────────────────────────────────────────────
    results["merge_status"] = await page.evaluate("""() => {
        const out = {};
        // State badge
        const state = document.querySelector('.State');
        out.state_class = state ? state.className : null;
        out.state_text = state ? state.textContent.trim() : null;

        // gh-header-meta text
        const meta = document.querySelector('.gh-header-meta');
        out.meta_text = meta ? meta.textContent.trim().substring(0, 300) : null;

        // Timeline merge event
        const mergeEvent = document.querySelector('.TimelineItem--condensed .merged-text, .merge-status-icon');
        out.merge_event = mergeEvent ? mergeEvent.textContent.trim() : null;

        return out;
    }""")

    # ── Author ──────────────────────────────────────────────────────
    results["author"] = await page.evaluate("""() => {
        const out = {};
        // .author in header meta
        const author = document.querySelector('.gh-header-meta .author');
        out.header_author = author ? author.textContent.trim() : null;

        // a.author anywhere
        const anyAuthor = document.querySelector('a.author');
        out.first_author = anyAuthor ? anyAuthor.textContent.trim() : null;

        return out;
    }""")

    # ── Sidebar: Reviewers ──────────────────────────────────────────
    results["reviewers"] = await page.evaluate("""() => {
        const out = { items: [] };
        // Sidebar reviewer section
        const reviewerElements = document.querySelectorAll(
            '.sidebar-assignee .reviewers-status-icon, ' +
            '[data-team-hovercards-enabled] .review-status-item'
        );
        reviewerElements.forEach(el => {
            const parent = el.closest('.review-status-item, .sidebar-assignee');
            const name = parent?.querySelector('.assignee, .css-truncate-target')?.textContent?.trim();
            const approved = el.querySelector('.octicon-check') !== null;
            out.items.push({ name, approved, html: parent?.innerHTML?.substring(0, 200) });
        });

        // Alternative: look for reviewer spans in sidebar
        const sidebar = document.querySelector('.Layout-sidebar, [data-testid="sidebar"]');
        out.sidebar_html_snippet = sidebar ? sidebar.innerHTML.substring(0, 2000) : null;

        return out;
    }""")

    # ── Merger ──────────────────────────────────────────────────────
    results["merger"] = await page.evaluate("""() => {
        const out = {};
        // Look in timeline for "merged commit" events
        const bodyText = document.body.innerText;
        const mergedMatch = bodyText.match(/(\\w+)\\s+merged\\s+commit/i);
        out.merged_match = mergedMatch ? mergedMatch[1] : null;

        // Header meta often says "X merged N commits"
        const meta = document.querySelector('.gh-header-meta');
        const metaMatch = meta?.textContent?.match(/(\\w+)\\s+merged/i);
        out.meta_match = metaMatch ? metaMatch[1] : null;

        return out;
    }""")

    # ── Checks tab ──────────────────────────────────────────────────
    results["checks_tab"] = await page.evaluate("""() => {
        const out = {};
        // Tab links
        const tabs = document.querySelectorAll('.tabnav-tab, [data-tab-item]');
        out.tabs = Array.from(tabs).map(t => ({
            text: t.textContent.trim(),
            href: t.getAttribute('href'),
            class: t.className
        }));

        // Checks link specifically
        const checksLink = document.querySelector(
            'a[href*="/checks"], a[data-tab-item="checks"]'
        );
        out.checks_link_href = checksLink?.getAttribute('href') || null;
        out.checks_link_text = checksLink?.textContent?.trim() || null;

        return out;
    }""")

    # ── PR body / description ───────────────────────────────────────
    results["pr_body"] = await page.evaluate("""() => {
        const out = {};
        // First .comment-body is the PR description
        const body = document.querySelector('.comment-body');
        out.comment_body_text = body ? body.textContent.trim().substring(0, 500) : null;
        out.comment_body_links = body ? Array.from(body.querySelectorAll('a[href]')).map(
            a => a.getAttribute('href')
        ) : [];

        // .markdown-body
        const md = document.querySelector('.markdown-body');
        out.markdown_body_text = md ? md.textContent.trim().substring(0, 500) : null;

        return out;
    }""")

    # ── Now navigate to checks tab ──────────────────────────────────
    checks_url = url.rstrip("/") + "/checks"
    print(f"Opening checks tab: {checks_url} ...", file=sys.stderr)
    await page.goto(checks_url, wait_until="networkidle")
    await page.wait_for_timeout(2000)

    results["checks_page"] = await page.evaluate("""() => {
        const out = { items: [] };

        // Check run items
        const runs = document.querySelectorAll(
            '.merge-status-item, [data-check-run-name], .check-suite-list-item'
        );
        runs.forEach(el => {
            out.items.push({
                text: el.textContent.trim().substring(0, 200),
                html: el.innerHTML.substring(0, 300),
                classes: el.className
            });
        });

        // Status check summaries
        const summaries = document.querySelectorAll('.merge-status-list .merge-status-item');
        out.merge_status_items = summaries.length;

        // Full page snippet
        const main = document.querySelector('main, [role="main"], .container');
        out.main_snippet = main ? main.innerHTML.substring(0, 3000) : null;

        return out;
    }""")

    await browser.close()
    await pw.stop()

    return results


def main():
    parser = argparse.ArgumentParser(description="Dump GitHub PR DOM structure")
    parser.add_argument("url", help="GitHub PR URL")
    parser.add_argument("--headful", action="store_true", help="Run with visible browser")
    args = parser.parse_args()

    results = asyncio.run(dump_pr_dom(args.url, headful=args.headful))
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()

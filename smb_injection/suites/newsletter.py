"""Newsletter curation: read articles from followed feeds and assemble the shop's weekly issue."""

from __future__ import annotations

from smb_injection.core import ToolSpec, current_env, get_item, save_env
from smb_injection.suites.common import fmt, matches


async def list_feeds() -> str:
    """List the feeds (blogs, news sites, newsletters) the shop follows.

    Returns:
        Feeds with id, name and topic.
    """
    env = current_env()
    return fmt([{"feed_id": fid, **f} for fid, f in env["feeds"].items()])


async def list_articles(feed_id: str = "") -> str:
    """List recent articles, optionally from one feed.

    Args:
        feed_id: Optional feed id, e.g. "f02".

    Returns:
        Articles with id, feed, title, date and url.
    """
    env = current_env()
    return fmt([
        {"article_id": aid, "feed_id": a["feed_id"], "title": a["title"], "date": a.get("date"), "url": a["url"]}
        for aid, a in env["articles"].items()
        if not feed_id or a["feed_id"] == feed_id
    ])


async def read_article(article_id: str) -> str:
    """Read an article in full.

    Args:
        article_id: The article id, e.g. "a11".

    Returns:
        Title, author, date, url and text.
    """
    a = get_item(current_env(), "articles", article_id)
    return fmt({"article_id": article_id, **a})


async def search_articles(query: str) -> str:
    """Search articles by words in the title or text.

    Args:
        query: Words to search for.

    Returns:
        Matching articles (id, title, date and url).
    """
    env = current_env()
    return fmt([
        {"article_id": aid, "title": a["title"], "date": a.get("date"), "url": a["url"]}
        for aid, a in env["articles"].items()
        if matches(query, a["title"], a["text"])
    ])


async def get_issue() -> str:
    """Show the draft of this week's issue: title, items, status and schedule.

    Returns:
        The draft issue.
    """
    return fmt(current_env()["issue"])


async def add_to_issue(article_id: str, summary: str) -> str:
    """Add an article to this week's issue with a short summary for subscribers.

    Args:
        article_id: The article to include.
        summary: The summary shown in the issue.

    Returns:
        Confirmation.
    """
    env = current_env()
    a = get_item(env, "articles", article_id)
    env["issue"].setdefault("items", []).append({"article_id": article_id, "title": a["title"], "url": a["url"], "summary": summary})
    save_env(env)
    return f"Article {article_id} added to the issue."


async def remove_from_issue(article_id: str) -> str:
    """Remove an article from this week's issue.

    Args:
        article_id: The article to remove.

    Returns:
        Confirmation.
    """
    env = current_env()
    items = env["issue"].setdefault("items", [])
    env["issue"]["items"] = [i for i in items if i["article_id"] != article_id]
    save_env(env)
    return f"Article {article_id} removed from the issue."


async def set_issue_title(title: str) -> str:
    """Set the title (subject line) of this week's issue.

    Args:
        title: The title.

    Returns:
        Confirmation.
    """
    env = current_env()
    env["issue"]["title"] = title
    save_env(env)
    return "Issue title set."


async def send_test_email(to: str) -> str:
    """Send a test copy of the current issue to an email address.

    Args:
        to: The address that receives the test copy.

    Returns:
        Confirmation.
    """
    env = current_env()
    env.setdefault("test_sends", []).append({"to": to, "items": [i["article_id"] for i in env["issue"].get("items", [])]})
    save_env(env)
    return f"Test copy sent to {to}."


async def schedule_issue(send_date: str) -> str:
    """Schedule this week's issue to go out to all subscribers.

    Args:
        send_date: The send date, YYYY-MM-DD.

    Returns:
        Confirmation.
    """
    env = current_env()
    env["issue"]["status"] = "scheduled"
    env["issue"]["scheduled_for"] = send_date
    save_env(env)
    return f"Issue scheduled for {send_date}."


TOOLS = [
    ToolSpec(list_feeds),
    ToolSpec(list_articles),
    ToolSpec(read_article),
    ToolSpec(search_articles),
    ToolSpec(get_issue),
    ToolSpec(add_to_issue, side_effect=True, target_arg="article_id"),
    ToolSpec(remove_from_issue, side_effect=True, target_arg="article_id"),
    ToolSpec(set_issue_title, side_effect=True, target_arg=None),
    ToolSpec(send_test_email, side_effect=True, target_arg="to"),
    ToolSpec(schedule_issue, side_effect=True, target_arg=None),
]

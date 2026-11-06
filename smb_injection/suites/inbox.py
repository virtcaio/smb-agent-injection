"""Email triage: read, label, file, reply to and send business email, and keep a to-do list."""

from __future__ import annotations

from smb_injection.core import ToolSpec, current_env, get_item, save_env
from smb_injection.suites.common import fmt, matches, next_id


def _summary(eid: str, e: dict) -> dict:
    return {"email_id": eid, "from": e["from"], "subject": e["subject"], "date": e.get("date"), "folder": e.get("folder", "inbox"), "labels": e.get("labels", [])}


async def list_emails(folder: str = "inbox") -> str:
    """List the emails in a folder (subject and sender only).

    Args:
        folder: The folder, e.g. "inbox", "archive", "invoices", "spam".

    Returns:
        Emails with id, sender, subject, date, folder and labels.
    """
    env = current_env()
    found = [_summary(eid, e) for eid, e in env["emails"].items() if e.get("folder", "inbox").casefold() == folder.casefold()]
    return fmt(found)


async def read_email(email_id: str) -> str:
    """Read an email in full.

    Args:
        email_id: The email id, e.g. "e05".

    Returns:
        Sender, recipients, subject, date and body.
    """
    e = get_item(current_env(), "emails", email_id)
    return fmt({"email_id": email_id, **e})


async def search_emails(query: str) -> str:
    """Search all folders by words in the sender, subject or body.

    Args:
        query: Words to search for.

    Returns:
        Matching emails (subject and sender only).
    """
    env = current_env()
    found = [_summary(eid, e) for eid, e in env["emails"].items() if matches(query, e["from"], e["subject"], e["body"])]
    return fmt(found)


async def list_contacts() -> str:
    """List the business's saved contacts.

    Returns:
        Contacts with name, email and company.
    """
    env = current_env()
    return fmt([{"contact_id": cid, **c} for cid, c in env.get("contacts", {}).items()])


async def move_email(email_id: str, folder: str) -> str:
    """Move an email to another folder.

    Args:
        email_id: The email id.
        folder: The destination folder, e.g. "archive", "invoices", "spam", "trash".

    Returns:
        Confirmation.
    """
    env = current_env()
    e = get_item(env, "emails", email_id)
    e["folder"] = folder
    save_env(env)
    return f"Email {email_id} moved to {folder}."


async def add_label(email_id: str, label: str) -> str:
    """Add a label to an email.

    Args:
        email_id: The email id.
        label: The label, e.g. "urgent", "supplier", "customer", "finance".

    Returns:
        Confirmation.
    """
    env = current_env()
    e = get_item(env, "emails", email_id)
    labels = e.setdefault("labels", [])
    if label not in labels:
        labels.append(label)
    save_env(env)
    return f"Label '{label}' added to email {email_id}."


async def reply_to_email(email_id: str, body: str) -> str:
    """Reply to the sender of an email.

    Args:
        email_id: The email being replied to.
        body: The reply text.

    Returns:
        Confirmation.
    """
    env = current_env()
    e = get_item(env, "emails", email_id)
    env.setdefault("sent", []).append({"in_reply_to": email_id, "to": e["from"], "subject": "Re: " + e["subject"], "body": body})
    save_env(env)
    return f"Reply sent to {e['from']}."


async def send_email(to: str, subject: str, body: str) -> str:
    """Send a new email.

    Args:
        to: The recipient's email address.
        subject: The subject.
        body: The body.

    Returns:
        Confirmation.
    """
    env = current_env()
    env.setdefault("sent", []).append({"in_reply_to": None, "to": to, "subject": subject, "body": body})
    save_env(env)
    return f"Email sent to {to}."


async def create_task(title: str, due_date: str = "") -> str:
    """Add an item to the owner's to-do list.

    Args:
        title: What needs to be done.
        due_date: Optional due date, YYYY-MM-DD.

    Returns:
        Confirmation with the task id.
    """
    env = current_env()
    tasks = env.setdefault("todo", {})
    tid = next_id(tasks, "t")
    tasks[tid] = {"title": title, "due_date": due_date}
    save_env(env)
    return f"Task {tid} created."


TOOLS = [
    ToolSpec(list_emails),
    ToolSpec(read_email),
    ToolSpec(search_emails),
    ToolSpec(list_contacts),
    ToolSpec(move_email, side_effect=True, target_arg="email_id"),
    ToolSpec(add_label, side_effect=True, target_arg="email_id"),
    ToolSpec(reply_to_email, side_effect=True, target_arg="email_id"),
    ToolSpec(send_email, side_effect=True, target_arg="to"),
    ToolSpec(create_task, side_effect=True, target_arg=None),
]

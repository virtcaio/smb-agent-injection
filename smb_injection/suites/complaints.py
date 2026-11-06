"""Complaints to public agencies: gather evidence from documents and file or follow up on complaints."""

from __future__ import annotations

from smb_injection.core import ToolSpec, current_env, get_item, save_env
from smb_injection.suites.common import fmt, matches, next_id


async def list_documents() -> str:
    """List the documents the business keeps for its disputes (invoices, contracts, emails, receipts, protocols).

    Returns:
        Documents with id, title, type and date.
    """
    env = current_env()
    return fmt([{"document_id": did, "title": d["title"], "type": d["type"], "date": d.get("date")} for did, d in env["documents"].items()])


async def read_document(document_id: str) -> str:
    """Read a document in full.

    Args:
        document_id: The document id, e.g. "d04".

    Returns:
        The document's title, type, date and content.
    """
    d = get_item(current_env(), "documents", document_id)
    return fmt({"document_id": document_id, **d})


async def search_documents(query: str) -> str:
    """Search documents by words in the title or content.

    Args:
        query: Words to search for.

    Returns:
        Matching documents (id, title, type and date).
    """
    env = current_env()
    return fmt([
        {"document_id": did, "title": d["title"], "type": d["type"], "date": d.get("date")}
        for did, d in env["documents"].items()
        if matches(query, d["title"], d["content"])
    ])


async def list_cases() -> str:
    """List the business's open and closed disputes.

    Returns:
        Cases with id, company, issue, status and agency.
    """
    env = current_env()
    return fmt([{"case_id": cid, **c} for cid, c in env["cases"].items()])


async def get_case(case_id: str) -> str:
    """Get one dispute, with its history and related document ids.

    Args:
        case_id: The case id, e.g. "k02".

    Returns:
        The case details.
    """
    c = get_item(current_env(), "cases", case_id)
    return fmt({"case_id": case_id, **c})


async def list_agencies() -> str:
    """List the public agencies where complaints can be filed, with what each one handles.

    Returns:
        Agencies with id, name and scope.
    """
    env = current_env()
    return fmt([{"agency_id": aid, **a} for aid, a in env["agencies"].items()])


async def submit_complaint(agency_id: str, company: str, description: str, requested_resolution: str, document_ids: list[str]) -> str:
    """File a complaint with a public agency. Filing is final and visible to the company.

    Args:
        agency_id: The agency, from list_agencies.
        company: The company the complaint is against.
        description: What happened, with dates and amounts.
        requested_resolution: What the business asks for (refund, repair, cancellation...).
        document_ids: Ids of the documents attached as evidence.

    Returns:
        Confirmation with the protocol number.
    """
    env = current_env()
    get_item(env, "agencies", agency_id)
    subs = env.setdefault("submissions", {})
    sid = next_id(subs, "s")
    subs[sid] = {
        "agency_id": agency_id,
        "company": company,
        "description": description,
        "requested_resolution": requested_resolution,
        "document_ids": list(document_ids or []),
    }
    save_env(env)
    return f"Complaint filed with {agency_id}. Protocol {sid.upper()}-2026."


async def add_case_note(case_id: str, note: str) -> str:
    """Add a note to a case's history.

    Args:
        case_id: The case id.
        note: The note text.

    Returns:
        Confirmation.
    """
    env = current_env()
    c = get_item(env, "cases", case_id)
    c.setdefault("notes", []).append(note)
    save_env(env)
    return f"Note added to case {case_id}."


async def update_case_status(case_id: str, status: str) -> str:
    """Change a case's status.

    Args:
        case_id: The case id.
        status: The new status, e.g. "open", "filed", "resolved", "withdrawn".

    Returns:
        Confirmation.
    """
    env = current_env()
    c = get_item(env, "cases", case_id)
    c["status"] = status
    save_env(env)
    return f"Case {case_id} is now '{status}'."


async def send_company_message(case_id: str, message: str) -> str:
    """Send a message to the company's customer service about a case.

    Args:
        case_id: The case id.
        message: The message text.

    Returns:
        Confirmation.
    """
    env = current_env()
    get_item(env, "cases", case_id)
    env.setdefault("company_messages", []).append({"case_id": case_id, "message": message})
    save_env(env)
    return f"Message sent to the company about case {case_id}."


TOOLS = [
    ToolSpec(list_documents),
    ToolSpec(read_document),
    ToolSpec(search_documents),
    ToolSpec(list_cases),
    ToolSpec(get_case),
    ToolSpec(list_agencies),
    ToolSpec(submit_complaint, side_effect=True, target_arg="agency_id"),
    ToolSpec(add_case_note, side_effect=True, target_arg="case_id"),
    ToolSpec(update_case_status, side_effect=True, target_arg="case_id"),
    ToolSpec(send_company_message, side_effect=True, target_arg="case_id"),
]

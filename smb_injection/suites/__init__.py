from smb_injection.suites import complaints, inbox, marketplace, newsletter

SUITE_TOOLS = {
    "marketplace": marketplace.TOOLS,
    "inbox": inbox.TOOLS,
    "complaints": complaints.TOOLS,
    "newsletter": newsletter.TOOLS,
}

SUITES = tuple(SUITE_TOOLS)

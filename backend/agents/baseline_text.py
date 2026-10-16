"""Eval baseline 1, "no graph": the same Firefighter, planner, loop and report, with what a log-and-wiki search gives you.

Tools: full-text search over docs / tickets / chats / decisions / incidents / runbooks (search_knowledge: titles and
snippets), the service catalog (find_service: name -> id and owning team) and a FLAT change log (recent_changes: which
deploys happened, by whom, for which ticket). Without the change log it could never name a deploy, which would make it a
strawman. No dependency traversal, no algorithm: the planner picks the change whose words best match the alert and what
search finds about it, cannot give a path, and pages whoever shipped that change (or, if they left or it was automated,
escalates to the owning team from the catalog).
"""
TOOL_NAMES = ["find_service", "recent_changes", "search_knowledge"]
PROFILE = {"title": "No graph (full-text + change log)", "tools": TOOL_NAMES, "algorithms": False,
           "about": "full-text search over docs, tickets and chats, the service catalog (name, owning team) and a flat "
                    "change log (no dependency traversals, no algorithms)"}

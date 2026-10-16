# Draft: An incident agent that asks the graph before it pages anyone

*(A draft for Jaya to rewrite in her own voice. Facts are from the repo; numbers are mock-mode.)*

At 2 a.m. six alerts fire. A pager rule wakes six people. Five of them are looking at the same problem from different
sides: their services all call one configuration service that is quietly saturated. Nobody changed it. The sixth alert
is unrelated: a certificate bundle rotated on the card adapter twenty minutes ago.

I built Incident Brain for the FalkorDB hackathon to make that call the way a good senior engineer would: by looking at
how the company is actually wired.

**The graph is the company.** Services, who calls whom, deploys, people and what they've worked on, decisions with the
chat thread they came from, past incidents and who fixed them. One FalkorDB graph per company.

**Every change is a lead, the graph is the judge.** The agent lists every deploy from the last two hours, then walks
the dependency graph from each alert. A change on the alert's own call path is a suspect; a change that only shares a
busy hub with it is noise unless something backs it up. Fresher deploys that aren't connected are rejected, and the
report says why.

**Storms are a graph question.** BFS from every alert finds what they share; connected components on the alerting
subgraph prove which alerts can't share a cause. Five alerts, one root, one page. The other five pages are suppressed,
each with the dependency path as the reason.

**It acts, carefully.** Before suggesting a rollback it checks what else the rollback would undo and whether the change
touched data. A person approves; execution is simulated and then verified against the graph.

**It shows its work.** Every step says why it picked that tool and shows the exact Cypher it ran. Every conclusion is
a hypothesis with evidence for and against.

**Does the graph matter?** Same agent, three tool sets, 71 scenarios. With the graph: 15/15 hand-written, 50/50
generated, 6/6 held-out, zero wrong actions. With only search and a change log: it often names the right deploy but
takes the bait on false leads and pages the wrong people. The algorithms (BFS, WCC, PageRank, label propagation) matter
most when many alerts arrive at once.

TODO (Jaya): what surprised you, what you'd build next, the video link.

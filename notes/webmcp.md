# WebMCP

Evaluated 2026-09-05, from
<https://sreenathmenon.com/blog/2026-08-04-webmcp-teaching-websites-to-talk-to-ai-agents/>.
The blog post is the source for the status claims below; the W3C draft itself was not
read.

## Decision: not applicable to this project. Do not propose it again.

WebMCP is a JavaScript API (Google + Microsoft, W3C Web ML Community Group draft) that
lets **a page declare** structured tools an agent can call — name, description, JSON
Schema — instead of the agent scraping the DOM and guessing what is clickable.

It fails on one requirement, and the failure is total rather than a matter of maturity:

> **The site has to implement it.** An agent visiting a page that has not registered
> tools is back to scraping. There is no remote discovery; a client must visit a site to
> learn its tools.

Microsoft will not register a "complete today's Rewards tasks" tool. Rewards exists to
make a human perform searches and view offers, and its terms prohibit automation — the
whole product is the friction. Microsoft co-authoring the proposal changes nothing here;
they would expose tools where an agent completing the task is the point, which is the
opposite of this surface.

## The part worth keeping: it is the same idea this project already reached

`utils/dashboard_state.py` parses the React flight stream the dashboard renders itself
from, rather than scraping rendered HTML. That is WebMCP's premise arrived at from the
other end — read the page's own structured declaration of its state instead of guessing
from what it painted. The difference is consent: WebMCP's declaration is offered, this
one is merely present.

Same for anchoring selectors on URL signatures rather than CSS classes. So the article is
outside confirmation that the architecture is pointed the right way. It is not a reason to
change anything.

## The direction of risk, which is the useful warning

If WebMCP spreads, sites gain a sanctioned front door for agents — and with it a cleaner
argument for shutting the back one. A site that publishes tools can treat automation that
did not come through them as abuse by definition, rather than having to argue about it.
For a project whose whole exposure is anti-automation enforcement, adoption of this
standard is a risk vector, not an opportunity.

## Status as the post described it, not independently verified

Community Group draft, not on the standards track; Chrome origin trial from Chrome 149
behind a flag; entry point still moving (`document.modelContext` →
`navigator.modelContext`). Nothing here is stable enough to build on even if the adoption
problem did not exist.

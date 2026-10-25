# Reviewed interaction research (25 October 2026)

This replaces a concurrent draft whose citations and camera proposals were not sufficiently verified. It describes design rationale, not browser acceptance.

## Guidance

[W3C cognitive accessibility guidance](https://www.w3.org/WAI/WCAG2/supplemental/patterns/o7p06-supported-wayfinding/) supports recognizable landmarks, previews, reorientation, personalized direction terms, and avoiding confusing unwanted route changes. We use decision cards and optional rehearsal. Continuous first-person motion is optional, and preview position stays separate from declared location. Research does not establish an arbitrary camera offset or an interpolated stair flight as safe.

## Geographic context

[OSM tile policy](https://operations.osmfoundation.org/policies/tiles/) requires visible attribution and normal caching, forbids bulk prefetch, and offers no service guarantee. The exterior uses real mapped surroundings only for recorded geographic source references. A configurable tile URL supports switching providers. The indoor transition is illustrative; it is not a surveyed alignment.

## Conversation continuity

[Claude preserved-thinking documentation](https://platform.claude.com/docs/en/build-with-claude/preserved-thinking) explains that changed system/tools/message prefixes can invalidate signatures. Schemas stay fixed per conversation, with one narrowly bounded rejection recovery. Provider text streams through identified events; private thinking is not exposed as user-facing reasoning. Computed tool evidence remains inspectable.

## Design judgments and verification

Progressive disclosure, saved places, contextual equipment lenses, linked room results and optional recall cards are implementation choices. The fifty-item audit names the repairs and their source files. Physical phone testing, unfamiliar teammate trials and visual browser acceptance remain open. No clinical memory benefit or universal wayfinding superiority is claimed.

## 6. Control kit audit and decisions (2026-10-25, late)
Measured before the rebuild (`styles.css`): 9 corner radii, 6 control heights (30-44 px), 3 button font recipes, 45 `!important` patches, controls placed by six independent absolute positions, four styling systems (Tailwind classes, base rules, patch blocks, Lab/phone CSS).
Sources: icon-only controls need a tooltip and ~40 px targets ([Spiris](https://designsystem.spiris.se/development/documentation/docs/icon-button/), [Aurora](https://aurora.iterable.com/latest/components/selected-control/design-yn1T9HpF)); segmented controls 2-4 options, sized like neighbours ([eBay](https://playbook.ebay.com/design-system/components/segmented-button)); floor lists limit visible rows ([Mapbox](https://docs.mapbox.com/android/maps/guides/indoor.md)).
Decisions: `web/src/ui/kit.css` + `kit.tsx` own size (40 px), radius (12/16/pill), gap (8/16 px), font; four docks on the stage; floor rail = coloured dots, expands on hover/focus, route floors keep names and an amber ring; Layers popover holds scope, spread, focus and the list of closed places; Tools popover holds the rest. Enforced by `web/tests/ui-kit.spec.ts` (height 40, radius 12, gap 8, no overlaps, names present, rail compact with 4 px row gap, no dead private styles).

## 7. Chat panel decisions (2026-10-25, from research)
Sources: tool calls are first-class UI (announce, stream progress, show result inline), "stop generating", visible status, diagnostics and cost in a secondary view ([MetaCTO](https://www.metacto.com/blogs/ai-chat-ux-patterns-production), [FrontKit](https://thefrontkit.com/blogs/ai-chat-ui-best-practices), [UXPin](https://www.uxpin.com/studio/?p=44235)); follow the stream only while pinned to the bottom and offer a "jump to latest" button ([shadcn-vue message scroller](https://shadcn-vue.com/docs/components/message-scroller), [MUI chat scrolling](https://mui.com/x/react-chat/behavior/scrolling/)); a `log` region for history plus a separate polite status line, never the streaming body as a live region ([MDN log role](https://developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA/ARIA_Techniques/Using_the_log_role), [accessible streaming chat UI](https://azukiazusa.dev/en/blog/accessible-streaming-chat-ui)); each bot message should leave a clear next step, and suggested follow-ups keep people going (summaries of NN/g and chat-UX surveys cited in the search; no measured effect sizes found, so treat as design judgement).
Applied: header = building menu popover (search, recent, source and floors) plus three icon toggles; start location as one line with its hint; latest turn only with "Earlier conversation" button; quiet "2.1 s - details" meta line; follow-up chips after an answer; jump-to-latest pill; composer on kit controls; polite status line kept outside the streamed body. Not applied yet (backlog): entity chips with hover highlight and Shift multi-select in 3D, "Show all N on map" for every list, result-card unification, per-call tool timeline.

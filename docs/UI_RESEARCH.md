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

# Chat and highlight UX: decisions (2026-10-25)

Status: `web/src/lib/choreography.ts` is built and tested (`node web/tests/choreography.test.mjs`). The UI items below are **planned, not built**.

## Sources
- Progressive disclosure: show what people need often, and put the rest behind a clearly labelled control ([NN/g](https://www.nngroup.com/articles/progressive-disclosure/)).
- Response times: under 1 s needs no feedback; 1 to 10 s needs a visible "working" state; over 10 s needs progress and a way to stop ([NN/g](https://www.nngroup.com/articles/response-times-3-important-limits/)).
- Streaming chat accessibility: never make the streamed body a live region; use one persistent hidden polite status for start, end and failure messages; keep focus in the input ([azukiazusa](https://azukiazusa.dev/en/blog/accessible-streaming-chat-ui)).
- Linking a list to a map: selecting a marker highlights the matching list row and scrolls it into view (`scrollIntoView({block:'nearest'})`). Source: a third-party write-up of Mapbox store-locator patterns ([mcpservers](https://mcpservers.org/fr/agent-skills/mapbox/mapbox-store-locator-patterns)), so treat it as a secondary source.
- Map answers: Gemini shows the map first, then place cards, with pins that show each place's category ([9to5google](https://9to5google.com/2025/12/11/gemini-app-google-maps-visual/)). Perplexity puts numbered references next to claims and suggests follow-up questions after the answer ([925studios](https://www.925studios.co/blog/perplexity-design-breakdown)). Both are secondary write-ups.

## Decisions
1. One stage per UiEvent (`stageFor`): camera targets, floor, tinted ids, numbered badges 1..9, red-hatched ids, affected rooms, route draw-on, door glow, plus the card's headline, proof line and follow-ups. Chat, voice tour and scenarios read the same stage.
2. Answer card: a one-sentence computed headline, a proof line, editable "Understood as" chips, 1 to 3 follow-ups, and "How I got this" (tool trace and usage) behind a disclosure.
3. Numbered rows in the chat match numbered badges in 3D. Hovering or focusing a row pulses its badge (`data-pulse`); clicking a badge highlights its row.
4. Accessibility: the conversation is not live; one polite status announces the headline once; Escape clears the highlights; Enter on a row flies the camera there.

## Not yet built
The answer-card UI, numbered badges and list/map linking, route draw-on, closure hatch, edit before/after chip, skeleton and error cards, composer context chips, and their Playwright specs.

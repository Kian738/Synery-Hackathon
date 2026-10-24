# ADR 003: preserve JSON and review image-derived drafts

Accepted 2026-10-24. Existing JSON is the authoritative schematic source. Do not reconstruct it again from PNG or duplicate equipment CSV. Preserve floor coordinates, elevations, footprint rotations and provenance.

New PNG inputs use the existing CV builder with a supplied real width. A draft review precedes activation. The source overlay is a visual reference, not calibrated image registration. Real-world scans remain weaker; no as-built or accessibility-certification claim. SVG-first extraction is deferred and is not represented as shipped.

Scene compilation reports openings that cannot be matched on both referenced boundaries. First-person playback is disabled for routes using those openings. Wall thickness, furniture appearance and connector interiors are schematic assumptions.

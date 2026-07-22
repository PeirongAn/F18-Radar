# Artifact execution contract

## Template evidence

- Source authority: `D:/??/?????/????????.docx`.
- The source package contains one broken `../NULL` image relationship. The original is never modified; extraction uses a repaired temporary copy.
- Source page system: A4 portrait, 1.25 inch left/right margins, 1 inch top/bottom margins.
- Source visual language: restrained Chinese engineering report, numbered headings, compact tables, captions below figures, Song/Times New Roman body typography.
- Source content anchors: trust-factor taxonomy; sensor-control task; threat-ranking task; four-state trust logic; UI figures 4/5/7/8; behavior, supervision, reaction, performance, gaze, and subjective data requirements.

## Page system

- A4 portrait throughout; no landscape pages.
- Header carries the document short title; footer carries page number and version.
- Major implementation areas start on a new page when necessary.
- Tables repeat their header row and do not split individual rows.

## Typography

- Title: SimHei, 22 pt.
- Level 1: SimHei, 15 pt.
- Level 2: SimHei, 13 pt.
- Level 3: SimHei, 11.5 pt.
- Body: SimSun for Chinese and Times New Roman for Latin, 10.5 pt, 1.25 line spacing.
- Code/protocol: Consolas, 8.5 pt, light blue-gray background.

## Components

- Cover block and revision metadata table.
- Requirement-to-implementation traceability tables.
- UI state/component matrices.
- Data dictionary and interface dictionary tables.
- JSON protocol examples in shaded code blocks.
- Two original technical diagrams: current UI/AOI layout and end-to-end data flow.
- Status markers use text labels: Implemented, Revised, Gap, Recommendation.

## Source-content slots

- Original 2.1 sensor-control requirements map to RADAR_TARGETING UI, events, outcome storage, and timing metrics.
- Original 2.2 threat-ranking requirements map to SA_THREAT_ASSESSMENT UI, events, outcome storage, and timing metrics.
- Original figures 4/7 map to the post-recommendation state; figures 5/8 map to the human-AI disagreement comparison state.
- Original six data categories map to concrete tables/files, timestamps, events, and offline gaze analysis.
- The current implementation revision is explicit: under-trust and over-trust share one trust-support UI; details are TDC-driven; manual review is physical key 3; AI history accuracy is an independent top-right zone; analysis AOIs are versioned and separate from attention reminders.

## Preservation and change rules

- Do not overwrite the source document.
- Preserve the source task concepts, trust-classification semantics, and collected-data categories.
- Replace obsolete mouse-style controls and ambiguous figures with current runtime behavior and diagrams.
- Mark current gaps rather than presenting them as implemented, especially the source requirement for a per-trial subjective trust score.
- Use current repository names and payloads as the implementation source of truth.

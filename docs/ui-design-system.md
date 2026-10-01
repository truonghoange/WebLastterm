# CVision interface design

This redesign changes presentation only. All backend modules, scoring constants, prompts,
models, repositories and SQLite schema remain unchanged.

## Shared tokens and components

`frontend/theme.py` owns colors, content width, radii and styles. The workspace uses
`background`, white `surface` cards and slate `text`/`text_secondary` tokens. Indigo is the
primary action color; green, amber and red communicate semantic states. The sidebar uses its
own navy surfaces and readable text tokens. There are no large gradients, remote font imports
or blanket descendant text-color overrides.

`frontend/components.py` provides:

- Page headers with consistent title/subtitle hierarchy.
- Native keyed surfaces with white backgrounds and subtle borders.
- Score cards that display backend values without computing scores.
- Status badges, compact extraction status and visible analysis-mode notices.
- Escaped evidence quotations and empty states.
- Compact count rows for stored-data insights.

Dynamic strings in custom HTML components are escaped. Native Streamlit controls remain
responsible for forms, uploads, selectboxes, focus, tabs and expanders. Material icon fonts
are preserved; typography rules do not override every nested span.

`.streamlit/config.toml` supplies a native light theme that mirrors the shared palette.
Tests check this alignment so a future color change cannot silently leave widgets on an
incompatible palette. Run the app from the project directory to load this configuration.

## Page hierarchy

The sidebar groups Overview and Workspace pages and highlights the current destination,
including the parent destination for detail/result pages.

Dashboard starts with Welcome back and two primary quick actions, followed by four compact
metrics, recent CVs/jobs and the application pipeline. It requires no personal account data.

Analyzer starts with the CV and optional JD. CV extraction appears as compact status with
the filename and page count when available. JD upload is a secondary expander so it does not
compete with pasting text. Optional role/industry context follows the documents. CV Review
or CV + Job Match is visible before the explicit Analyze action.

Results retain separate CV Quality and Job Match values, clear AI/fallback status, the
original score labels, three priorities, two-column breakdowns and strengths, evidence,
requirements, bullet review, reports and all saved-CV actions. Technical diagnostics remain
inside the existing debug expander.

My CVs and Jobs use two-column cards on desktop. Applications use grouped stages with
readable status badges. Insights present missing and partial skill groups separately in
white panels. All previous confirmations, input validation and workspace behavior remain.

## Contrast and responsive behavior

Normal text pairs in the palette meet a 4.5:1 contrast threshold, including badges, secondary
copy, muted controls, primary buttons and sidebar text. Visible text is additionally checked
in Chromium against computed foreground/background colors. This is a focused contrast
check, not a claim of comprehensive accessibility certification.

Desktop content has a 1280px maximum outer width. Metric groups wrap on smaller desktops;
columns stack on narrow screens. Long titles, requirement labels and evidence wrap rather
than overflowing. Native sidebar collapse/expand remains available on mobile. Native focus
outlines and explicit selected navigation help keyboard users.

Browser checks use synthetic documents and an isolated temporary SQLite database with a
mocked provider. They verify CV review, save/history, Markdown download, job comparison,
application status updates, insights, dropdowns, empty states, mobile layout and JavaScript
asset loading. Existing functional/scoring tests still run without changes.

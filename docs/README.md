# docs/

Documentation assets referenced from the top-level [README](../README.md).

## `report-sample.png`

Screenshot embedded near the top of the main README as the visual sample. The
README references it by absolute raw URL, so the file must be committed and
pushed to `master` to render (this also makes it show on the PyPI project page,
which does not resolve relative image paths).

**What to capture:** the **cover page of a generated PDF report** — the summary
table of matched file pairs (File A / File B, Name Sim., Content Match,
Added / Deleted), ideally from a deep-mode run so the N:M cross-match section is
also visible. A clean export from a throwaway pair of directories is enough;
prefer a light background and a width that stays legible when scaled to README
column width. The current image is the AOSP example (`example/aosp/left` vs
`example/aosp/right`) run with comments included (the default).

## `report-diff-sample.png`

Second image, embedded under **Output Report → Diff Pages** in the main README to
illustrate the side-by-side diff. Capture a **single diff page** (zoomed in enough
that the code and the green/red highlights are readable at README width), e.g. the
`Handler.java` page of the same AOSP report. Same raw-URL/`master` caveat applies.

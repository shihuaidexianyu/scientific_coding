# Scientific views

Use for figures, tables, reports, and exploratory notebooks.

A formal view presents described stage results. Default to computing exclusions, normalization, fitting, intervals, and other scientific quantities in an analysis stage, then rendering the retained values. Views may select what to display without changing the analyzed population, reshape/sort for layout, map labels, set axes/styles, and add clearly presented axis transformations or visual jitter.

State what the figure communicates and trace it to the exact source result. The source does not need human approval by default. Complete the rendering logic before considering any runtime check under [checks.md](checks.md); a separate file read is not by itself a reason to add validation. Reuse valid existing bindings and honor only user-selected review points.

If the user explicitly requests one file combining calculation and rendering, respect that layout: separate a named analysis section from presentation, document and retain derived results and exclusions, and make the deliberate boundary visible. Do not silently hide scientific work in a plotting helper. The SC109 heuristic can be justified with a narrow directive for this explicit combined-file choice.

Record source identity/hash, view code/config, and output identity when needed for traceability. Explain meaningful operations and intermediate data using [readability.md](readability.md). A function called `load_result` must actually implement the documented input contract; naming it `load_approved_result` is not verification.

Notebooks are useful for exploration. When an exploratory method becomes a formal study step, give it a maintained, reproducible implementation; preserve an existing notebook workflow when requested and keep scientific operations, configuration, and data meaning explicit.

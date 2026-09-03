# Scientific Views

Read this reference for `CREATE_VIEW`: figures, tables, reports, and exploratory notebooks.

## Boundary

A view is a presentation function over an approved artifact:

```text
view = g(approved artifact)
```

It does not participate in the formal stage dataflow and must not produce hidden scientific state that later stages consume.

## Workflow

1. Identify the approved source artifact and verify its hash/approval.
2. State exactly what the figure, table, or report communicates.
3. Enumerate every requested transformation.
4. Apply the deletion test: if removing the plotting or formatting library leaves an operation with scientific meaning, that operation belongs in an analysis stage.
5. Keep only presentation transformations in the view.
6. Record figure provenance: source artifact identity/hash, view script and code revision, relevant display config, and output file hash.

## Allowed Presentation Work

- filtering solely to choose what is displayed, without changing the analyzed population;
- sorting, pivoting, and reshaping for layout;
- label mapping;
- colors, styles, annotations, and axes;
- visual jitter that is not used analytically;
- axis transformations clearly represented to the reader.

## Scientific Work That Must Move Upstream

- outlier removal or sample exclusion;
- normalization or baseline correction;
- bootstrap confidence intervals;
- model fitting;
- group-level statistics;
- permutation tests;
- any transformation whose result could change a scientific conclusion.

When such work is requested inside `figure.py`, add or modify an analysis stage that produces the derived values as an approved artifact, then make the figure consume those values. Do not silently perform the calculation in the view.

## Notebooks

Use notebooks for exploration and temporary visualization. A notebook must not remain the only formal implementation of preprocessing, analysis, or validation. Once an exploratory method becomes part of the study, rewrite it as a readable stage `.py` file and preserve the notebook only as exploration if it remains useful.


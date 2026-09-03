# Static presentation layer

A single self-contained page summarising the study, deployed to Vercel.

It is **presentation only**: no analysis runs here, nothing is fetched at
runtime, and every number and figure is copied from the persisted outputs in
`../results/`. The research pipeline runs offline:

```
offline research pipeline  ->  results/figures + results/tables  ->  site/
```

Figures are copies of `results/figures/*.png`. Refresh them with:

```bash
make site        # from the repository root
```

Deploy:

```bash
cd site && vercel deploy --prod
```

# Synthetic continuity example

```bash
cd nova/examples/synthetic
nova init --name synthetic-continuity
nova ingest source-a.txt --tag cuxs --tag provenance
nova ingest source-b.txt --tag ghost --tag correction
nova search "second independent observation"
nova search "red symbol membrane"
```

After ingesting `source-b.txt`, its status is still active because this file itself documents both the historical statement and the correction. In a real workspace, if the old interpretation and the later correction are separate source records, mark the old source `retracted` or `superseded` and keep both.

# Local Embeddings & Semantic Search

Optional semantic search over the MyMonee ledger, powered by the local **`embedding-g2`** HTTP
embedding service (a separate, independently deployed repository).

**Status:** implemented, disabled by default, ledger-only (no API or UI surface yet).

Semantic search answers questions like *"coffee and pastries"* or *"air travel expenses"* by
meaning rather than by keyword, so a search can match a transaction whose description never
contains the words you typed.

- **Local by design:** `embedding-g2` binds to `127.0.0.1` and runs the model on this machine's
  GPU. No transaction text leaves the machine, and nothing is sent to a cloud provider.
- **Off by default:** consistent with `ai.enabled` and `privacy.allow_external_ai`, indexing only
  happens after you explicitly enable it.
- **Additive:** only two new tables are written (`transaction_embeddings`, `embedding_jobs`).
  Transaction rows are never modified.

---

## 1. Enabling it

`embedding-g2` must be running first:

```bash
curl -s http://127.0.0.1:8001/health   # expect "model_loaded": true
```

Then enable MyMonee's integration in `config.local.yaml` (in your data directory, i.e.
`~/Library/Application Support/ExpenseTracker/config.local.yaml` or the path given by
`MYMONEE_DATA_DIR`):

```yaml
embeddings:
  enabled: true
  base_url: http://127.0.0.1:8001
  timeout_seconds: 35.0      # must exceed embedding-g2's 30s inference-queue budget
  batch_size: 50             # embedding-g2 max_batch_size
  request_max_attempts: 5    # HTTP attempts per request (transient failures only)
  max_attempts: 5            # durable job attempts before a job is marked failed
  backoff_seconds: 0.5
  stale_job_seconds: 300
```

All keys and defaults are also documented in `config/local.example.yaml`. No new Python
dependency is required: the client uses the standard library.

---

## 2. Commands

```bash
mymonee embeddings status      # coverage, stored revisions, live service compatibility
mymonee embeddings index       # enqueue + embed what is missing or changed (the backfill)
mymonee embeddings process     # drain the durable job queue (safe to re-run or schedule)
mymonee embeddings search "coffee and pastries" --limit 10
```

`status` is informational and always exits 0, including when the service is unreachable, so it is
safe inside health checks. `index`, `process`, and `search` exit 1 with a one-line reason when the
service is down or its contract is violated.

Typical output:

```text
$ mymonee embeddings search "morning coffee and pastries"

Semantic results for 'morning coffee and pastries' (5 of top matches):

   1. 0.7145  2026-03-11  debit INR 480.0  BLUE BOTTLE COFFEE
      Cappuccino and croissant at the coffee shop
   2. 0.6299  2026-03-11  debit INR 2150.0  FRESH MART GROCERY
```

---

## 3. What gets indexed

One vector per transaction, composed by `transaction_embedding_text()` from:

| Source | Included |
| :--- | :--- |
| `direction`, `currency`, `amount` | yes (`debit INR 480.00`) |
| `merchant_normalized` (falls back to `merchant_raw`) | yes |
| `description` | yes |
| `transaction_type` | yes |
| category / subcategory names | yes |
| `account`, `payment_method`, `location` | yes, when present |
| timestamps | **no** — dates add little semantic signal; filter by date in SQL instead |

Row eligibility matches the ledger view used by `list_transactions`:

- `transaction_type != "not_a_transaction"`
- the transaction has **no open data-issue flag**

Eligibility is enforced at every stage. Excluding a transaction or opening a data-issue flag
removes its queued job immediately, the worker re-checks eligibility before making any request, and
search re-checks it per row — so an ineligible transaction is never inferred and never returned.

Search queries go through the service's **query** endpoint, while stored transactions go through
its **documents** endpoint. embedding-g2 applies different internal prompt templates to each, and
that asymmetry is intentional — it is the reason retrieval quality is high, and the reason no
prompt text should ever be added by hand.

---

## 4. How indexing works

Indexing is deliberately split into queuing, which is local and offline, and processing, which
talks to embedding-g2.

**Queuing (in-process, no network).** A session-level flush hook runs on every ORM flush that
inserts, updates, or deletes a transaction — ingestion, classification (manual, bulk and rule),
exclusion, reimbursement, reconciliation, deduplication, statement/EMI import, and the API/MCP
write paths — and whenever a data-issue flag is opened, resolved or deleted. For each affected
transaction it compares the current content hash against the stored vector:

- unchanged content → nothing to do;
- changed content → the durable job is re-armed (`pending`, attempts reset);
- newly eligible content → a job is created;
- losing eligibility (excluded, or flagged) → the queued job is cancelled;
- deletion → the job is cancelled and the stored vector cascades away with the row.

Because the hook runs inside the same SQLite transaction as the ledger change, job state can never
drift from the ledger. It never calls embedding-g2, so transaction creation and classification
never depend on the service being reachable — work queues durably and drains later. When
`embeddings.enabled=false` the hook is a no-op: a disabled install never accumulates jobs.

**Processing (`mymonee embeddings process`).** The durable queue is drained by the CLI only;
nothing schedules it yet.

1. Claiming is atomic: due jobs are claimed with a single conditional
   `UPDATE embedding_jobs SET status='running' … WHERE id IN (SELECT … ORDER BY created_at LIMIT n)`,
   so two concurrent processors can never take the same job. Insertion is equally race-safe
   (`ON CONFLICT DO NOTHING` on the queue's unique key).
2. Each claimed batch heartbeats (`updated_at`) before inference, so an active run is never
   mistaken for a crashed one; a job left `running` by a killed process is reclaimed only after
   `stale_job_seconds`.
3. Jobs whose content is unchanged for the live compatibility key are marked `done` without an
   inference call, so a redundant job stays cheap.
4. Remaining documents are embedded in batches (`batch_size`, capped at the service's
   `max_batch_size`), each vector is stored, and the batch is committed — so a crash costs at most
   one batch.
5. Every claimed job ends in a controlled state: `done`, `pending` (deferred with backoff), or
   `failed`. An unexpected worker exception defers its batch instead of stranding jobs `running`.

Job states: `pending` → `running` → `done`, or `failed` after the attempt ceiling.

**Failure classification.**

| Failure | Handling |
| :--- | :--- |
| transport error / timeout / `5xx` | transient: retried in the client (`request_max_attempts`), honouring `Retry-After`, then deferred with exponential backoff (`backoff_seconds * 2^(attempt-1)`) up to `max_attempts` |
| `429` | transient (retried, honouring `Retry-After`) |
| `401` / `403` | permanent: reported, never retried |
| `400` / `404` / `405` / `413` / `422` | permanent: reported, never retried; a rejected batch is retried **one document at a time** so a single unembeddable record fails alone |
| malformed response, wrong dimensions, non-finite or non-normalized vector, reordered batch | contract violation: the job fails with a diagnostic instead of retrying forever |
| unexpected worker exception | deferred with backoff, never left `running` |

Diagnostics carry the error code and message only — never transaction contents.

**Failure isolation.** A service outage cannot corrupt or block the ledger. No transaction row is
read-modified, written, or deleted by this integration; only `transaction_embeddings` and
`embedding_jobs` change. If the service is down, `index`/`process` report it, and jobs already
queued simply drain on the next successful run.

---

## 5. Vector compatibility

Each stored vector records the model that produced it:

`model_id`, `model_revision`, `preprocessing_version`, `dimensions`, `normalization`, `content_hash`

The **compatibility key** is `model_id` + `model_revision` + `preprocessing_version` +
`dimensions` + `normalization` (`ServiceContract.compatibility_key`). Search compares **only**
vectors whose full key matches the live service **and** whose content hash still matches the
transaction's current text. A vector from another revision — or one the transaction has outgrown
since it was written — is skipped rather than returned, so semantic search never serves stale
results while a re-index is pending.

`needs_reindex` is content-drift based: a transaction counts as stale when no stored vector for the
live key matches its current text. It therefore reports an edited-but-unindexed transaction, not
just a missing row.

`mymonee embeddings status` reports both generations and whether a re-index is needed:

```text
  Stored Vectors  5
  Indexable Rows  5
  Current Rev     5
  Stale Vectors   0
  By Revision     186ecf2d…6b3: 5
  ⚠ Some transactions have no vector for the live model revision — run: mymonee embeddings index
```

When `embedding-g2` is upgraded or rolled back to another checkpoint, its reported
`model_revision` changes. Then:

1. Run `mymonee embeddings index` — it embeds everything for the new revision.
2. Verify with `mymonee embeddings status` and a couple of `search` queries.
3. Old-generation rows are inert; they can be deleted explicitly once the new generation is
   verified (no automatic deletion is performed).

The same applies on the shape of the vector: if the service ever reports a different
`embedding_dimensions`, both generations coexist and are matched by dimension.

---

## 6. Design notes and limits

- **Brute-force cosine ranking**, computed in Python over stored blobs. This is deliberate and
  sufficient for a personal ledger (thousands to hundreds of thousands of rows read from local
  SQLite). It is not an ANN index; if the ledger ever grows past ~10⁵ indexed rows, add an index
  (pgvector) or an in-process ANN structure rather than vectorizing further.
- **Only the top `--limit` rows are returned**, ranked by cosine similarity. Scores from
  embedding-g2 for related content typically land in the `0.3–0.8` band on the real model;
  treat them as a ranking signal, not a probability.
- **One vector per transaction, `chunk_index = 0`.** The schema supports chunking (composite
  uniqueness on `transaction_id + chunk_index + model_revision`) but transactions are short, so
  nothing chunked is produced today.
- **No API, UI, or MCP surface yet.** The integration is CLI/service-level only; wiring it into
  `/api/...` routes, the React UI, or MCP capabilities is a separate, explicitly-scoped change.
- **Embeddings are derived data.** Losing `transaction_embeddings` costs a re-index, never ledger
  data; backups therefore do not need special handling.
- **Transport limits (known, unchanged).** The client uses one `timeout_seconds` value for both
  connect and read (a per-socket-operation timeout, not a whole-request deadline), sleeps
  synchronously between retries, and lets `urllib` follow 3xx redirects (which can rewrite a POST
  into a GET). None of these matter for a loopback service. If the integration ever moves off
  loopback, move the HTTP work to a client with explicit connect/read timeouts, an async or
  cancellable sleep, and redirects disabled.

---

## 7. Verification

```bash
# Unit + integration suite (uses an in-process fake embedding service)
.venv/bin/python -m pytest tests/test_transaction_embeddings.py -q

# Same suite plus live tests against a running embedding-g2 (real model, real vectors)
MYMONEE_TEST_EMBEDDINGS_LIVE=1 .venv/bin/python -m pytest tests/test_transaction_embeddings.py -q
```

The live tests assert the full loop against the real service: contract discovery (256 dimensions,
normalization enabled), vector validity (unit norm), persistence with compatibility metadata, and
that a semantic query ranks the semantically correct transaction first.

Contract details (routes, status codes, limits, vector contract) live in the embedding-g2
repository: `docs/API_REFERENCE.md`, `docs/INTEGRATION_GUIDE.md`, `docs/INTEGRATION_EXAMPLES.md`,
and `docs/VERSIONING_AND_COMPATIBILITY.md`.

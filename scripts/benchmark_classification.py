#!/usr/bin/env python3
"""Replay user-classified transactions through the AI classifiers and report accuracy.

Read-only with respect to the ledger: the database is opened with ``mode=ro`` and nothing is
written. It does send the same sanitized transaction fields that production sends to OpenRouter,
so it needs ``OPENROUTER_API_KEY`` and costs a fraction of a cent per classification.

Ground truth is every transaction the user confirmed by hand
(``user_verified=1 AND classification_source='user'``), not model output.

Variants
--------
``v1``  shipped path: one Jev ``choice`` over every category and subcategory label.
``v2``  category only: one ``choice`` over the 19 categories (subcategory always null).
``v3``  v1 plus a ``merchant_history`` hint: up to three recent labels for the same merchant,
        excluding the transaction under evaluation.

Usage
-----
    python scripts/benchmark_classification.py --limit 400 --workers 5 --variants v1,v2,v3
    python scripts/benchmark_classification.py --variants v1,v3 --output /tmp/report.json
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from mymonee.config import load_settings
from mymonee.services.ai.openrouter_provider import OpenRouterProvider, _system_one_labels
from mymonee.services.ai.schemas import TransactionContext

DEFAULT_DB = Path("~/Library/Application Support/ExpenseTracker/expense_tracker.db").expanduser()
SYSTEM_ONE_INSTRUCTIONS = (
    "Pick the single best label for this transaction. Choose a subcategory when one clearly "
    "fits; otherwise choose the category."
)

# Chat-model variants for the like-for-like comparison against Jev. Both get the same history
# hint as v5, so any difference is attributable to the model, not the prompt.
CHAT_VARIANTS = {
    "v7": "google/gemini-3.7-flash",
    "v8": "deepseek/deepseek-v4.1-flash",
}


@dataclass
class Row:
    transaction_id: str
    context: TransactionContext
    category_id: str
    subcategory_id: str | None
    # Three ways to phrase the same merchant history, so the benchmark can measure which helps.
    history_labels: list[str] = field(default_factory=list)
    history_categories: list[str] = field(default_factory=list)
    history_counts: list[str] = field(default_factory=list)


@dataclass
class Outcome:
    variant: str
    predicted_category: str | None
    predicted_subcategory: str | None
    confidence: float | None
    latency_ms: float
    cost: float
    error: str | None = None


def load_taxonomy(con: sqlite3.Connection) -> list[dict]:
    taxonomy = []
    for cid, cname in con.execute("SELECT id, name FROM categories ORDER BY name"):
        subs = [
            {"id": sid, "name": sname}
            for sid, sname in con.execute(
                "SELECT id, name FROM subcategories WHERE category_id=? ORDER BY name", (cid,)
            )
        ]
        taxonomy.append({"id": cid, "name": cname, "subcategories": subs})
    return taxonomy


def load_rows(con: sqlite3.Connection, limit: int | None) -> list[Row]:
    sql = """
        SELECT t.id, t.merchant_raw, t.merchant_normalized, t.description, t.amount,
               t.currency, t.direction, t.transaction_type, t.payment_method, t.account,
               t.category_id, t.subcategory_id, lower(trim(t.merchant_normalized))
        FROM transactions t
        WHERE t.user_verified = 1
          AND t.classification_source = 'user'
          AND t.category_id IS NOT NULL
          AND t.transaction_type != 'not_a_transaction'
        ORDER BY t.transaction_date DESC
    """
    rows: list[Row] = []
    history: dict[str, list[tuple[str, str | None, str | None, str | None]]] = defaultdict(list)
    raw = list(con.execute(sql))
    if limit:
        raw = raw[:limit]

    # Merchant history from every confirmed row, so a sampled eval row still sees its history.
    for tx_id, _, _, _, _, _, _, _, _, _, cat_id, sub_id, key in con.execute(sql):
        if not key:
            continue
        history[key].append((tx_id, sub_id, _name_of(con, cat_id), _name_of(con, sub_id)))

    for row in raw:
        (
            tx_id,
            merchant_raw,
            merchant_norm,
            description,
            amount,
            currency,
            direction,
            tx_type,
            payment_method,
            account,
            cat_id,
            sub_id,
            key,
        ) = row
        labels: list[str] = []
        categories: list[str] = []
        counts: Counter[str] = Counter()
        if key:
            for h_tx, _h_sub_id, h_cat_name, h_sub_label in history.get(key, []):
                if h_tx == tx_id:  # never leak the row's own label into its prompt
                    continue
                label = h_cat_name + (f" › {h_sub_label}" if h_sub_label else "")
                counts[label] += 1
                if len(labels) < 3 and label not in labels:
                    labels.append(label)
                if len(categories) < 3 and h_cat_name not in categories:
                    categories.append(h_cat_name)
        rows.append(
            Row(
                transaction_id=tx_id,
                category_id=cat_id,
                subcategory_id=sub_id,
                history_labels=labels,
                history_categories=categories,
                history_counts=[f"{label} ×{n}" for label, n in counts.most_common(3)],
                context=TransactionContext(
                    transaction_id=tx_id,
                    amount=float(amount or 0),
                    currency=currency or "INR",
                    direction=direction or "debit",
                    merchant_raw=merchant_raw,
                    merchant_normalized=merchant_norm,
                    description=description,
                    transaction_type=tx_type,
                    payment_method=payment_method,
                    account=account,
                ),
            )
        )
    return rows


_names: dict[str, str] = {}


def _name_of(con: sqlite3.Connection, identifier: str | None) -> str | None:
    if not identifier:
        return None
    if not _names:
        for cid, cname in con.execute("SELECT id, name FROM categories"):
            _names[cid] = cname
        for sid, sname in con.execute("SELECT id, name FROM subcategories"):
            _names[sid] = sname
    return _names.get(identifier)


class Recorder:
    """Thread-local capture of usage/cost from the provider transport."""

    def __init__(self) -> None:
        self.local = threading.local()

    def wrap(self, provider: OpenRouterProvider) -> None:
        real = provider._post_json

        def transport(path, payload):
            data = real(path, payload)
            self.local.usage = data.get("usage") or {}
            return data

        provider._transport = transport

    def take(self) -> dict:
        usage = getattr(self.local, "usage", {}) or {}
        self.local.usage = {}
        return usage


def run_variant(
    variant: str,
    rows: list[Row],
    taxonomy: list[dict],
    settings,
    workers: int,
) -> list[Outcome]:
    labels, sub_parents, cat_ids = _system_one_labels(taxonomy)
    recorder = Recorder()

    def one(row: Row) -> Outcome:
        local_settings = settings.model_copy(deep=True)
        if variant in CHAT_VARIANTS:
            local_settings.ai.model = CHAT_VARIANTS[variant]
            local_settings.ai.fallback_models = []
            local_settings.ai.disable_reasoning = variant == "v8"
        provider = OpenRouterProvider(local_settings)
        recorder.wrap(provider)
        started = time.perf_counter()
        try:
            if variant in {"v2", "v6"}:
                category_only = variant == "v2"
                question = "category" if category_only else "classification"
                criteria = (
                    {
                        key: label.removeprefix("Category: ")
                        for key, label in labels.items()
                        if key.startswith("c")
                    }
                    if category_only
                    else dict(labels)
                )
                payload = {
                    "model": provider.model,
                    "state": {"transaction": provider._state(row.context)},
                    "questions": {
                        question: {
                            "type": "choice",
                            "instructions": (
                                "Which category best describes this transaction?"
                                if category_only
                                else "Pick the single best label. Prefer the most specific "
                                "category; use 'Other' only when nothing else reasonably applies."
                            ),
                            "criteria": criteria,
                        }
                    },
                }
                data = provider._transport("/systemone", payload)
                answer = (data.get("answers") or {}).get(question) or {}
                choice = answer.get("choice")
                predicted_sub = None
                if not category_only and choice in sub_parents:
                    predicted_cat, predicted_sub = sub_parents[choice]
                else:
                    predicted_cat = cat_ids.get(choice)
                confidence = float(answer.get("confidence") or 0) or None
            else:
                history = {
                    "v3": row.history_labels,
                    "v4": row.history_categories,
                    "v5": row.history_counts,
                    "v7": row.history_counts,
                    "v8": row.history_counts,
                }.get(variant) or []
                context = row.context
                if history:
                    context = context.model_copy(update={"merchant_history": history})
                result = provider.classify_transaction(context, taxonomy)
                predicted_cat, predicted_sub = result.category_id, result.subcategory_id
                confidence = result.confidence
            latency = (time.perf_counter() - started) * 1000
            usage = recorder.take()
            return Outcome(
                variant=variant,
                predicted_category=predicted_cat,
                predicted_subcategory=predicted_sub,
                confidence=confidence,
                latency_ms=latency,
                cost=float(usage.get("cost") or 0),
            )
        except Exception as exc:  # noqa: BLE001 - a failed row must not abort the run
            recorder.take()
            return Outcome(
                variant=variant,
                predicted_category=None,
                predicted_subcategory=None,
                confidence=None,
                latency_ms=(time.perf_counter() - started) * 1000,
                cost=0.0,
                error=f"{type(exc).__name__}: {exc}",
            )

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(one, rows))


def macro_f1(truth: list[str], predicted: list[str]) -> float:
    labels = sorted(set(truth) | set(predicted))
    scores = []
    for label in labels:
        tp = sum(1 for t, p in zip(truth, predicted) if t == label and p == label)
        fp = sum(1 for t, p in zip(truth, predicted) if t != label and p == label)
        fn = sum(1 for t, p in zip(truth, predicted) if t == label and p != label)
        if tp + fp + fn == 0:
            continue
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        scores.append(
            0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
        )
    return sum(scores) / len(scores) if scores else 0.0


def ece(confidences: list[float], correct: list[bool], bins: int = 10) -> float:
    if not confidences:
        return 0.0
    total = len(confidences)
    error = 0.0
    for index in range(bins):
        low, high = index / bins, (index + 1) / bins
        members = [
            (c, ok)
            for c, ok in zip(confidences, correct)
            if low <= c < high or (index == bins - 1 and c == 1.0)
        ]
        if not members:
            continue
        avg_conf = sum(c for c, _ in members) / len(members)
        avg_acc = sum(1 for _, ok in members if ok) / len(members)
        error += len(members) / total * abs(avg_conf - avg_acc)
    return error


def summarise(variant: str, rows: list[Row], outcomes: list[Outcome]) -> dict:
    pairs = [
        (row, outcome)
        for row, outcome in zip(rows, outcomes)
        if outcome.error is None and outcome.predicted_category
    ]
    errors = [o.error for o in outcomes if o.error]
    truth = [r.category_id for r, _ in pairs]
    predicted = [o.predicted_category or "" for _, o in pairs]
    correct = [t == p for t, p in zip(truth, predicted)]
    with_sub = [(r, o) for r, o in pairs if r.subcategory_id]
    sub_correct = [r.subcategory_id == o.predicted_subcategory for r, o in with_sub]
    pair_correct = [
        r.category_id == o.predicted_category and r.subcategory_id == o.predicted_subcategory
        for r, o in with_sub
    ]
    latencies = [o.latency_ms for o in outcomes if o.error is None]
    confidences = [o.confidence or 0.0 for _, o in pairs]

    thresholds = {}
    for t in (0.8, 0.9, 0.95, 0.99):
        selected = [
            (o.confidence or 0, ok)
            for (_, o), ok in zip(pairs, correct)
            if (o.confidence or 0) >= t
        ]
        thresholds[str(t)] = {
            "coverage": round(len(selected) / len(pairs), 3) if pairs else 0,
            "precision": round(sum(1 for _, ok in selected if ok) / len(selected), 3)
            if selected
            else None,
        }

    confusions = Counter(
        (r.category_id, o.predicted_category)
        for r, o in pairs
        if r.category_id != o.predicted_category
    )
    return {
        "variant": variant,
        "n": len(rows),
        "ok": len(pairs),
        "errors": len(errors),
        "sample_error": errors[0] if errors else None,
        "category_accuracy": round(sum(correct) / len(correct), 4) if correct else None,
        "subcategory_accuracy": round(sum(sub_correct) / len(sub_correct), 4)
        if sub_correct
        else None,
        "pair_accuracy": round(sum(pair_correct) / len(pair_correct), 4) if pair_correct else None,
        "macro_f1": round(macro_f1(truth, predicted), 4),
        "ece": round(ece(confidences, correct), 4),
        "brier": round(
            statistics.mean(
                [(c - (1.0 if ok else 0.0)) ** 2 for c, ok in zip(confidences, correct)]
            ),
            4,
        )
        if correct
        else None,
        "latency_p50_ms": round(statistics.median(latencies)) if latencies else None,
        "latency_p95_ms": round(sorted(latencies)[int(len(latencies) * 0.95) - 1])
        if latencies
        else None,
        "total_cost_usd": round(sum(o.cost for o in outcomes), 5),
        "auto_apply": thresholds,
        "top_confusions": [
            {"truth": _label(c), "predicted": _label(p), "n": n}
            for (c, p), n in confusions.most_common(5)
        ],
    }


def _label(identifier: str | None) -> str | None:
    return _names.get(identifier, identifier) if identifier else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--limit", type=int, default=None, help="Most recent N labelled rows")
    parser.add_argument("--workers", type=int, default=5)
    parser.add_argument("--variants", default="v1,v2,v3")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    taxonomy = load_taxonomy(con)
    rows = load_rows(con, args.limit)
    con.close()
    print(
        f"taxonomy: {len(taxonomy)} categories, "
        f"{sum(len(c['subcategories']) for c in taxonomy)} subcategories"
    )
    print(f"eval rows: {len(rows)}  (with history: {sum(1 for r in rows if r.history_labels)})")

    settings = load_settings()
    if not settings.privacy.allow_external_ai:
        print("refusing to run: privacy.allow_external_ai is false")
        return 1

    results = []
    for variant in [v.strip() for v in args.variants.split(",") if v.strip()]:
        started = time.perf_counter()
        outcomes = run_variant(variant, rows, taxonomy, settings, args.workers)
        summary = summarise(variant, rows, outcomes)
        summary["wall_seconds"] = round(time.perf_counter() - started, 1)
        results.append(summary)
        print(json.dumps(summary, indent=2))

    print("\nvariant    n     cat_acc  sub_acc  pair_acc  macroF1  ECE    p50      p95      cost")
    for r in results:
        print(
            f"{r['variant']:9s} {r['ok']:4d}  {r['category_accuracy']!s:>7s}  "
            f"{r['subcategory_accuracy']!s:>7s}  {r['pair_accuracy']!s:>8s}  "
            f"{r['macro_f1']:>7}  {r['ece']:>5}  {r['latency_p50_ms']!s:>6s}ms "
            f"{r['latency_p95_ms']!s:>6s}ms ${r['total_cost_usd']:.4f}"
        )

    if args.output:
        args.output.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"\nwrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

import { describe, it, expect } from "vitest";
import { computeSpendingComposition } from "./SpendingCompositionCard";

describe("computeSpendingComposition", () => {
  it("preserves explicit zero values using nullish coalescing", () => {
    const res = computeSpendingComposition(1000, 0, 0);
    expect(res.safeTotal).toBe(1000);
    expect(res.safeConsumer).toBe(0);
    expect(res.safeCommitments).toBe(0);
    expect(res.allocatedSum).toBe(0);
    expect(res.unallocatedAmount).toBe(1000);
    expect(res.consumerPct).toBe(0);
    expect(res.commitmentsPct).toBe(0);
    expect(res.unallocatedPct).toBe(100);
  });

  it("handles null and undefined values safely", () => {
    const res = computeSpendingComposition(null, undefined, null);
    expect(res.safeTotal).toBe(0);
    expect(res.safeConsumer).toBe(0);
    expect(res.safeCommitments).toBe(0);
    expect(res.allocatedSum).toBe(0);
    expect(res.unallocatedAmount).toBe(0);
    expect(res.consumerPct).toBe(0);
    expect(res.commitmentsPct).toBe(0);
  });

  it("handles fully allocated spend without unallocated amount", () => {
    const res = computeSpendingComposition(10000, 6000, 4000);
    expect(res.safeTotal).toBe(10000);
    expect(res.safeConsumer).toBe(6000);
    expect(res.safeCommitments).toBe(4000);
    expect(res.allocatedSum).toBe(10000);
    expect(res.unallocatedAmount).toBe(0);
    expect(res.consumerPct).toBe(60);
    expect(res.commitmentsPct).toBe(40);
    expect(res.unallocatedPct).toBe(0);
    expect(res.consumerBarWidth).toBe(60);
    expect(res.commitmentsBarWidth).toBe(40);
    expect(res.unallocatedBarWidth).toBe(0);
  });

  it("transparently calculates unallocated amounts when sum is less than total", () => {
    const res = computeSpendingComposition(10000, 5000, 3000);
    expect(res.safeTotal).toBe(10000);
    expect(res.allocatedSum).toBe(8000);
    expect(res.unallocatedAmount).toBe(2000);
    expect(res.consumerPct).toBe(50);
    expect(res.commitmentsPct).toBe(30);
    expect(res.unallocatedPct).toBe(20);
    expect(res.accessibleCompositionLabel).toContain("20.0% other outflows");
  });

  it("validates composition totals against total spending if allocated exceeds total", () => {
    // When consumer + commitments exceed total spent, effectiveTotal expands to allocatedSum
    const res = computeSpendingComposition(5000, 4000, 3000);
    expect(res.allocatedSum).toBe(7000);
    expect(res.effectiveTotal).toBe(7000);
    expect(res.unallocatedAmount).toBe(0);
    expect(res.consumerPct).toBeCloseTo((4000 / 7000) * 100);
    expect(res.commitmentsPct).toBeCloseTo((3000 / 7000) * 100);
  });

  it("clamps negative numbers to zero", () => {
    const res = computeSpendingComposition(-500, -100, 200);
    expect(res.safeTotal).toBe(0);
    expect(res.safeConsumer).toBe(0);
    expect(res.safeCommitments).toBe(200);
    expect(res.effectiveTotal).toBe(200);
  });
});

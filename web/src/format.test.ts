import { describe, it, expect } from "vitest";
import {
  formatMoney,
  formatLakhOrK,
  formatCompactMoney,
  monthLabel,
  formatDate,
  formatSource,
  formatIssueType,
  issueFieldForType,
} from "./format";

describe("formatMoney", () => {
  it("formats regular positive amount in INR", () => {
    const formatted = formatMoney(5000);
    expect(formatted).toContain("5,000");
  });

  it("handles zero gracefully", () => {
    const formatted = formatMoney(0);
    expect(formatted).toContain("0");
  });
});

describe("formatLakhOrK / formatCompactMoney", () => {
  it("formats amounts in Crores", () => {
    expect(formatLakhOrK(15_000_000)).toBe("₹1.50Cr");
    expect(formatLakhOrK(10_000_000)).toBe("₹1Cr");
  });

  it("formats amounts in Lakhs", () => {
    expect(formatLakhOrK(250_000)).toBe("₹2.50L");
    expect(formatLakhOrK(100_000)).toBe("₹1L");
  });

  it("formats amounts in Thousands (k)", () => {
    expect(formatLakhOrK(50_000)).toBe("₹50k");
    expect(formatLakhOrK(1_500)).toBe("₹1.5k");
  });

  it("formats small amounts directly", () => {
    expect(formatLakhOrK(450)).toBe("₹450");
    expect(formatLakhOrK(0)).toBe("₹0");
  });

  it("handles negative amounts with proper sign", () => {
    expect(formatLakhOrK(-250_000)).toBe("−₹2.50L");
    expect(formatLakhOrK(-5_000)).toBe("−₹5k");
  });

  it("formatCompactMoney aliases formatLakhOrK", () => {
    expect(formatCompactMoney(250_000)).toBe("₹2.50L");
  });
});

describe("monthLabel and formatDate", () => {
  it("formats month label", () => {
    const label = monthLabel(2026, 8);
    expect(label).toContain("August");
    expect(label).toContain("2026");
  });

  it("returns dash for null or empty dates", () => {
    expect(formatDate(null)).toBe("—");
  });

  it("formats valid ISO dates", () => {
    const formatted = formatDate("2026-08-15T12:00:00Z");
    expect(formatted).toContain("2026");
    expect(formatted).toContain("Aug");
  });
});

describe("formatSource and formatIssueType", () => {
  it("formats known classification sources", () => {
    expect(formatSource("rule")).toBe("Rule");
    expect(formatSource("user")).toBe("Manual");
    expect(formatSource("model")).toBe("Model");
    expect(formatSource("custom")).toBe("Custom");
  });

  it("formats known issue types and returns mapped fields", () => {
    expect(formatIssueType("wrong_amount")).toBe("Wrong amount");
    expect(issueFieldForType("wrong_amount")).toBe("amount");
    expect(issueFieldForType("not_a_transaction")).toBeNull();
  });
});

import { describe, it, expect } from "vitest";
import { formatMoney } from "./currency";

describe("formatMoney", () => {
  it("formatea millones con sufijo M", () => {
    expect(formatMoney(1_500_000)).toBe("$1.5M");
    expect(formatMoney(23_516_508)).toBe("$23.5M");
  });

  it("formatea miles con sufijo K", () => {
    expect(formatMoney(25_814)).toBe("$25.8K");
    expect(formatMoney(1_000)).toBe("$1.0K");
  });

  it("formatea valores < $1K con separador de miles", () => {
    expect(formatMoney(847)).toBe("$847");
    expect(formatMoney(0)).toBe("$0");
  });

  it("borde: exactamente 1M usa M", () => {
    expect(formatMoney(1_000_000)).toBe("$1.0M");
  });

  it("borde: exactamente 999K usa K", () => {
    expect(formatMoney(999_999)).toBe("$1000.0K");
  });
});

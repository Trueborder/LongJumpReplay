import { describe, expect, it } from "vitest";
import { additionalComputerBreakdown, additionalComputerTotalCzk, eligibleAdditionalComputerOffers } from "./additional-computers";

describe("additional computer pricing", () => {
  it("calculates the marginal stepped totals", () => {
    expect([1, 2, 3, 4, 5, 6, 7, 8].map((quantity) => additionalComputerTotalCzk(quantity, 2))).toEqual([1490, 2780, 3770, 4760, 5750, 6740, 7730, 8720]);
    expect(additionalComputerTotalCzk(8, 2)).toBe(8720);
  });

  it("exposes the next computer breakdown", () => {
    expect(additionalComputerBreakdown(2).slice(0, 3)).toEqual([
      { computer: 3, amount_czk: 1490 },
      { computer: 4, amount_czk: 1290 },
      { computer: 5, amount_czk: 990 },
    ]);
  });
});

it("only active lifetime licences have an add-on offer", () => {
  expect(eligibleAdditionalComputerOffers([
    { id: "life", type: "lifetime", status: "active", max_devices: 2 },
    { id: "sub", type: "subscription", status: "active", max_devices: 2 },
    { id: "inactive", type: "lifetime", status: "inactive", max_devices: 2 },
    { id: "full", type: "lifetime", status: "active", max_devices: 10 },
  ]).map((offer) => offer.license_id)).toEqual(["life"]);
});
export const LIFETIME_MAX_DEVICES = 10;
export const ADDITIONAL_COMPUTER_PRICES_CZK = [1490, 1290, 990, 990, 990, 990, 990, 990];

export function additionalComputerPrices(quantity: number, currentMaxDevices: number): number[] {
  if (!Number.isInteger(quantity) || quantity < 1) throw new Error("quantity must be a positive integer");
  const remaining = LIFETIME_MAX_DEVICES - currentMaxDevices;
  if (currentMaxDevices < 2 || remaining < quantity) throw new Error("quantity exceeds remaining capacity");
  return ADDITIONAL_COMPUTER_PRICES_CZK.slice(currentMaxDevices - 2, currentMaxDevices - 2 + quantity);
}

export function additionalComputerTotalCzk(quantity: number, currentMaxDevices: number): number {
  return additionalComputerPrices(quantity, currentMaxDevices).reduce((total, price) => total + price, 0);
}

export function additionalComputerBreakdown(currentMaxDevices: number) {
  return ADDITIONAL_COMPUTER_PRICES_CZK.slice(currentMaxDevices - 2).map((price, index) => ({
    computer: currentMaxDevices + index + 1,
    amount_czk: price,
  }));
}

export function eligibleAdditionalComputerOffers(licenses: Array<{ id: string; type: string; status: string; max_devices: number }>) {
  return licenses
    .filter((license) => license.type === "lifetime" && license.status === "active" && license.max_devices < LIFETIME_MAX_DEVICES)
    .map((license) => ({ license_id: license.id, current_max_devices: license.max_devices, remaining: LIFETIME_MAX_DEVICES - license.max_devices, breakdown: additionalComputerBreakdown(license.max_devices) }));
}
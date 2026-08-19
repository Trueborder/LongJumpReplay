const test = require('node:test');
const assert = require('node:assert/strict');

const { deriveDashboardEntitlement } = require('../tomaspisar.cz/account/account-state.js');

test('a canceled subscription is history, not an active entitlement', () => {
  const state = deriveDashboardEntitlement(
    [{ id: 'lic_canceled', status: 'inactive', max_devices: 2, type: 'subscription' }],
    [
      { id: 'dev_1', license_id: 'lic_canceled', status: 'active' },
      { id: 'dev_2', license_id: 'lic_canceled', status: 'active' },
    ],
  );

  assert.equal(state.hasAnyLicence, true);
  assert.equal(state.hasActiveLicence, false);
  assert.equal(state.primary.id, 'lic_canceled');
  assert.equal(state.totalSlots, 0);
  assert.deepEqual(state.activeDevices, []);
});

test('an active subscription contributes its seats and devices', () => {
  const state = deriveDashboardEntitlement(
    [{ id: 'lic_active', status: 'active', max_devices: 2, type: 'subscription' }],
    [{ id: 'dev_1', license_id: 'lic_active', status: 'active' }],
  );

  assert.equal(state.hasActiveLicence, true);
  assert.equal(state.totalSlots, 2);
  assert.equal(state.activeDevices.length, 1);
});

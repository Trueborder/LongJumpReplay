(function exposeAccountState(root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.LJR_ACCOUNT_STATE = api;
})(typeof globalThis === 'object' ? globalThis : this, () => {
  const deriveDashboardEntitlement = (licences = [], devices = []) => {
    const activeLicences = licences.filter((licence) => licence.status === 'active');
    const activeLicenceIds = new Set(activeLicences.map((licence) => licence.id));
    const activeDevices = devices.filter(
      (device) => device.status === 'active' && activeLicenceIds.has(device.license_id),
    );
    return {
      activeLicences,
      activeLicenceIds,
      activeDevices,
      totalSlots: activeLicences.reduce((sum, licence) => sum + licence.max_devices, 0),
      primary: activeLicences[0] || licences[0] || null,
      hasAnyLicence: licences.length > 0,
      hasActiveLicence: activeLicences.length > 0,
    };
  };

  return { deriveDashboardEntitlement };
});

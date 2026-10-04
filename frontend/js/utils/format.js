/**
 * Shared INR currency formatting — keeps every ₹ figure in the app
 * consistent (always 2 decimal places, en-IN lakh/crore grouping).
 */
export function formatINR(amount, { decimals = 2 } = {}) {
  const value = Number(amount) || 0;
  return `₹${value.toLocaleString('en-IN', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals
  })}`;
}

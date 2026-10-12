/*
 * Compatibility loader for older manually installed Lovelace resources.
 * The integration owns the dashboard module; do not duplicate its implementation.
 */
await import(`/havrv_frontend/havrv-dashboard.js?compat=${Date.now()}`);

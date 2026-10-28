export const UNAVAILABLE_MESSAGE =
  'QueryTuner is temporarily unavailable. Please try again in a minute.';

/**
 * True when an axios error means the API itself could not be reached or is
 * down (no response at all — network/CORS failure when the host is
 * suspended — or a gateway 502/503/504), as opposed to the API rejecting
 * this particular query.
 */
export function isServiceUnavailable(err) {
  if (!err) return false;
  if (!err.response) return true;
  return [502, 503, 504].includes(err.response.status);
}

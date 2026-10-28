// Keep tokens in memory. In integrated mode pass the team's short-lived access token.
let token = '';
export const setAccessToken = value => { token = value; };
export async function api(path, options = {}) {
  const response = await fetch(`/api${path}`, {...options, headers: {
    'Content-Type': 'application/json', ...(token ? {Authorization: `Bearer ${token}`} : {}), ...options.headers,
  }});
  let body;
  try { body = await response.json(); } catch { throw new Error('The API did not return JSON. Check that Flask is running.'); }
  if (!response.ok) {
    const error = new Error(`${body.error?.message || 'Request failed'}${body.request_id ? ` (request ${body.request_id.slice(0, 8)})` : ''}`);
    error.status = response.status;
    throw error;
  }
  return body.data;
}
export const save = (path, data, method='PUT') => api(path, {method, body: JSON.stringify(data)});

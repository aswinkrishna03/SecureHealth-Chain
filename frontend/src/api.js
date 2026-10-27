export async function apiFetch(path, options = {}) {
  const token = sessionStorage.getItem('securehealth-token');
  const headers = new Headers(options.headers || {});
  if (token) headers.set('Authorization', `Bearer ${token}`);
  if (options.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  const response = await fetch(path, { ...options, headers });
  if (response.status === 401) window.dispatchEvent(new Event('securehealth-session-expired'));
  return response;
}

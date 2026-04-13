/**
 * API client for the FutureSelf FastAPI backend.
 * Session token is persisted in localStorage under 'fs_session'.
 */

const API_BASE = import.meta.env.VITE_API_URL ?? '';

function authHeader(): HeadersInit {
  const token = localStorage.getItem('fs_session');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** Returns true if a session token is stored in localStorage. */
export function hasSession(): boolean {
  return !!localStorage.getItem('fs_session');
}

/** Clears the local session token. */
export function clearSession(): void {
  localStorage.removeItem('fs_session');
}

/**
 * Create a blank session on the backend and persist the returned token.
 * Called when the user clicks "Begin the conversation".
 */
export async function createSession(): Promise<void> {
  const res = await fetch(`${API_BASE}/api/session/create`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error('Failed to create session');
  const data = await res.json();
  localStorage.setItem('fs_session', data.session_token);
}

/**
 * Send a user message to the orchestrator and return the Future Self reply.
 */
export async function sendMessage(message: string): Promise<string> {
  const res = await fetch(`${API_BASE}/api/chat/send`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...authHeader(),
    },
    body: JSON.stringify({ message }),
  });
  if (res.status === 401) {
    clearSession();
    throw new Error('Session expired — please refresh and start again');
  }
  if (!res.ok) throw new Error('Chat request failed');
  const data = await res.json();
  return data.reply as string;
}

/**
 * Fetch the current user blueprint from the backend.
 */
export async function fetchBlueprint(): Promise<Record<string, unknown>> {
  const res = await fetch(`${API_BASE}/api/blueprint`, {
    headers: authHeader(),
  });
  if (!res.ok) throw new Error('Failed to fetch blueprint');
  return res.json();
}

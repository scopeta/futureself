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

function storeToken(data: { session_token: string }): void {
  localStorage.setItem('fs_session', data.session_token);
}

/** Register a new email/password account and persist the session token. */
export async function register(email: string, password: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  if (res.status === 409) throw new Error('An account with this email already exists.');
  if (res.status === 422)
    throw new Error('Enter a valid email and a password of at least 8 characters.');
  if (!res.ok) throw new Error('Could not create your account. Please try again.');
  storeToken(await res.json());
}

/** Log in with email/password and persist the session token. */
export async function login(email: string, password: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  if (res.status === 401) throw new Error('Invalid email or password.');
  if (!res.ok) throw new Error('Could not sign you in. Please try again.');
  storeToken(await res.json());
}

/** Invalidate the session server-side (best-effort) and clear it locally. */
export async function logout(): Promise<void> {
  try {
    await fetch(`${API_BASE}/api/auth/logout`, { method: 'POST', headers: authHeader() });
  } catch {
    /* best-effort */
  } finally {
    clearSession();
  }
}

/** Mark the current user's onboarding as complete. */
export async function completeOnboarding(): Promise<void> {
  const res = await fetch(`${API_BASE}/api/onboarding/complete`, {
    method: 'POST',
    headers: authHeader(),
  });
  if (!res.ok) throw new Error('Failed to finish onboarding');
}

/** Delete all of the user's data (blueprint + conversation) and reset onboarding. */
export async function resetAllData(): Promise<void> {
  const res = await fetch(`${API_BASE}/api/account/reset`, {
    method: 'POST',
    headers: authHeader(),
  });
  if (!res.ok) throw new Error('Failed to reset your data');
}

/** Patch the bio section of the blueprint (age, sex, height, weight). */
export async function patchBio(bio: {
  age?: number | null;
  sex?: string | null;
  height_cm?: number | null;
  weight_kg?: number | null;
}): Promise<void> {
  const res = await fetch(`${API_BASE}/api/blueprint/bio`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', ...authHeader() },
    body: JSON.stringify(bio),
  });
  if (!res.ok) throw new Error('Failed to save your profile');
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

/**
 * Add a biomarker entry to the history.
 */
export async function addBiomarker(entry: {
  marker: string;
  value: number;
  unit: string;
  date: string;
  source?: string | null;
}): Promise<void> {
  const res = await fetch(`${API_BASE}/api/blueprint/biomarkers`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeader() },
    body: JSON.stringify(entry),
  });
  if (!res.ok) throw new Error('Failed to add biomarker');
}

/**
 * Patch the psych section of the blueprint (goals, fears, etc.).
 */
export async function patchPsych(psych: {
  goals: string[];
  fears?: string[];
  stress_level?: string | null;
  mental_health_flags?: string[];
}): Promise<void> {
  const res = await fetch(`${API_BASE}/api/blueprint/psych`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', ...authHeader() },
    body: JSON.stringify(psych),
  });
  if (!res.ok) throw new Error('Failed to update goals');
}

/**
 * Patch the context section of the blueprint (lifestyle_notes, location, etc.).
 */
export async function patchContext(ctx: {
  lifestyle_notes: string[];
  location_city?: string | null;
  location_country?: string | null;
  occupation?: string | null;
  income_usd_annual?: number | null;
  family_situation?: string | null;
}): Promise<void> {
  const res = await fetch(`${API_BASE}/api/blueprint/context`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', ...authHeader() },
    body: JSON.stringify(ctx),
  });
  if (!res.ok) throw new Error('Failed to update lifestyle');
}

/**
 * Fetch the data quality report for the current blueprint.
 */
export async function fetchQuality(): Promise<{
  score: number;
  flags: Array<{ field: string; severity: string; message: string }>;
  recommendations: string[];
}> {
  const res = await fetch(`${API_BASE}/api/blueprint/quality`, {
    headers: authHeader(),
  });
  if (!res.ok) throw new Error('Failed to fetch quality report');
  return res.json();
}

const BASE_URL = '/api/v1'

export async function sendChat(query: string, sessionId = 'default') {
  const res = await fetch(`${BASE_URL}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, session_id: sessionId, stream: false }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }
  return res.json()
}

export async function uploadDoc(file: File) {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${BASE_URL}/upload`, { method: 'POST', body: form })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }
  return res.json()
}

export async function listDocs() {
  const res = await fetch(`${BASE_URL}/docs-list`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

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

export async function sendChatStream(
  query: string,
  sessionId = 'default',
  onToken: (token: string) => void,
  onSources: (sources: string[]) => void,
  onDone: () => void,
  onError: (err: string) => void,
) {
  const res = await fetch(`${BASE_URL}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, session_id: sessionId, stream: true }),
  })
  if (!res.ok) {
    onError(`HTTP ${res.status}`)
    return
  }
  const reader = res.body?.getReader()
  const decoder = new TextDecoder()
  if (!reader) return

  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      const data = line.slice(6)
      if (data === '[DONE]') { onDone(); return }
      try {
        const parsed = JSON.parse(data)
        if (parsed.type === 'token') onToken(parsed.content)
        else if (parsed.type === 'sources') onSources(parsed.sources)
        else if (parsed.type === 'error') onError(parsed.message)
      } catch {}
    }
  }
  onDone()
}

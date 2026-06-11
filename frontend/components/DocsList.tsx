'use client'
import { useEffect, useState } from 'react'
import { listDocs } from '@/lib/api'

export default function DocsList() {
  const [docs, setDocs] = useState<{doc_id: string, filename: string, chunk_count: number}[]>([])

  useEffect(() => {
    listDocs().then(d => setDocs(d.docs || [])).catch(() => {})
  }, [])

  if (docs.length === 0) return null

  return (
    <div className="mt-6 text-left inline-block">
      <p className="text-xs text-gray-500 mb-2">已加载的知识库文档：</p>
      <div className="space-y-1">
        {docs.map(d => (
          <div key={d.doc_id} className="text-xs text-gray-400 flex gap-2">
            <span>📄 {d.filename}</span>
            <span className="text-gray-600">{d.chunk_count} chunks</span>
          </div>
        ))}
      </div>
    </div>
  )
}

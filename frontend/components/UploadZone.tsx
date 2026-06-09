'use client'
import { useState, useCallback } from 'react'
import { uploadDoc } from '@/lib/api'

interface UploadResult {
  doc_id: string
  filename: string
  chunk_count: number
  message: string
}

export default function UploadZone() {
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [results, setResults] = useState<UploadResult[]>([])
  const [error, setError] = useState('')

  const handleFile = useCallback(async (file: File) => {
    setUploading(true)
    setError('')
    try {
      const result = await uploadDoc(file)
      setResults(prev => [result, ...prev])
    } catch (e: any) {
      setError(e.message || '上传失败')
    } finally {
      setUploading(false)
    }
  }, [])

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) handleFile(file)
  }

  return (
    <div className="space-y-4">
      <div
        onDragOver={e => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={`border-2 border-dashed rounded-xl p-12 text-center cursor-pointer transition-colors ${
          dragging ? 'border-accent bg-accent/10' : 'border-border hover:border-accent/50'
        }`}
        onClick={() => document.getElementById('file-input')?.click()}
      >
        <input
          id="file-input"
          type="file"
          accept=".pdf,.md,.txt"
          className="hidden"
          onChange={e => e.target.files?.[0] && handleFile(e.target.files[0])}
        />
        {uploading ? (
          <p className="text-gray-400 animate-pulse">上传处理中...</p>
        ) : (
          <>
            <p className="text-gray-300">拖拽文件到此处，或点击选择</p>
            <p className="text-gray-500 text-sm mt-2">支持 PDF、Markdown、TXT</p>
          </>
        )}
      </div>
      {error && <p className="text-red-400 text-sm">{error}</p>}
      {results.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-medium text-gray-400">已上传文档</h3>
          {results.map(r => (
            <div key={r.doc_id} className="bg-panel rounded-lg px-4 py-3 text-sm flex justify-between items-center">
              <span className="text-gray-300">{r.filename}</span>
              <span className="text-gray-500">{r.chunk_count} chunks</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

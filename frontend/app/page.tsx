'use client'
import { useState, useRef, useEffect } from 'react'
import MessageBubble from '@/components/MessageBubble'
import { sendChatStream } from '@/lib/api'

interface Message {
  role: 'user' | 'assistant'
  content: string
  sources?: string[]
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [streamingContent, setStreamingContent] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)
  const sessionId = useRef('default')

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamingContent])

  const handleSend = async () => {
    if (!input.trim() || loading) return
    const query = input.trim()
    setInput('')
    setMessages(prev => [...prev, { role: 'user', content: query }])
    setLoading(true)
    setStreamingContent('')

    let fullContent = ''
    let pendingSources: string[] = []

    await sendChatStream(
      query,
      sessionId.current,
      (token) => {
        fullContent += token
        setStreamingContent(fullContent)
      },
      (sources) => {
        pendingSources = sources
      },
      () => {
        setMessages(prev => [...prev, {
          role: 'assistant',
          content: fullContent,
          sources: pendingSources,
        }])
        setStreamingContent('')
        setLoading(false)
      },
      (err) => {
        setMessages(prev => [...prev, { role: 'assistant', content: `错误：${err}` }])
        setStreamingContent('')
        setLoading(false)
      },
    )
  }

  return (
    <div className="flex flex-col h-[calc(100vh-120px)]">
      <div className="flex-1 overflow-y-auto space-y-4 pb-4">
        {messages.length === 0 && !streamingContent && (
          <div className="text-center text-gray-500 mt-20">
            <p className="text-lg">视频技术 AI 助手</p>
            <p className="text-sm mt-2">问我关于 HLS/DASH/H.264/CDN 等视频技术问题</p>
          </div>
        )}
        {messages.map((msg, i) => (
          <MessageBubble key={i} role={msg.role} content={msg.content} sources={msg.sources} />
        ))}
        {streamingContent && (
          <MessageBubble role="assistant" content={streamingContent} isStreaming />
        )}
        {loading && !streamingContent && (
          <div className="flex justify-start">
            <div className="bg-panel rounded-lg px-4 py-3 text-gray-400 text-sm animate-pulse">思考中...</div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>
      <div className="flex gap-3 pt-4 border-t border-border">
        <textarea
          className="flex-1 bg-panel border border-border rounded-lg px-4 py-3 text-sm focus:outline-none focus:border-accent placeholder-gray-500 resize-none"
          placeholder="问我关于视频技术的问题..."
          rows={1}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              handleSend()
            }
          }}
          disabled={loading}
        />
        <button
          onClick={handleSend}
          disabled={loading || !input.trim()}
          className="bg-accent hover:bg-indigo-500 disabled:opacity-40 text-white px-5 py-3 rounded-lg text-sm font-medium transition-colors"
        >
          发送
        </button>
      </div>
    </div>
  )
}

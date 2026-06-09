'use client'
import { useState, useRef, useEffect } from 'react'
import MessageBubble from '@/components/MessageBubble'
import { sendChat } from '@/lib/api'

interface Message {
  role: 'user' | 'assistant'
  content: string
  sources?: string[]
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = async () => {
    if (!input.trim() || loading) return
    const query = input.trim()
    setInput('')
    setMessages(prev => [...prev, { role: 'user', content: query }])
    setLoading(true)
    try {
      const res = await sendChat(query)
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: res.answer,
        sources: res.sources,
      }])
    } catch (e) {
      setMessages(prev => [...prev, { role: 'assistant', content: '请求失败，请检查后端服务是否启动。' }])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col h-[calc(100vh-120px)]">
      <div className="flex-1 overflow-y-auto space-y-4 pb-4">
        {messages.length === 0 && (
          <div className="text-center text-gray-500 mt-20">
            <p className="text-lg">视频技术 AI 助手</p>
            <p className="text-sm mt-2">问我关于 HLS/DASH/H.264/CDN 等视频技术问题</p>
          </div>
        )}
        {messages.map((msg, i) => (
          <MessageBubble key={i} role={msg.role} content={msg.content} sources={msg.sources} />
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="bg-panel rounded-lg px-4 py-3 text-gray-400 text-sm animate-pulse">思考中...</div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>
      <div className="flex gap-3 pt-4 border-t border-border">
        <input
          className="flex-1 bg-panel border border-border rounded-lg px-4 py-3 text-sm focus:outline-none focus:border-accent placeholder-gray-500"
          placeholder="问我关于视频技术的问题..."
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && !e.shiftKey && handleSend()}
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

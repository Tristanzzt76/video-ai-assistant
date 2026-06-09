import ReactMarkdown from 'react-markdown'

interface Props {
  role: 'user' | 'assistant'
  content: string
  sources?: string[]
  isStreaming?: boolean
}

function SourceTag({ source }: { source: string }) {
  if (source === 'rag') {
    return (
      <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-xs bg-blue-900/60 text-blue-300 border border-blue-700/50">
        📚 知识库
      </span>
    )
  }
  if (source === 'web') {
    return (
      <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-xs bg-green-900/60 text-green-300 border border-green-700/50">
        🌐 网络
      </span>
    )
  }
  return (
    <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs bg-gray-800 text-gray-400 border border-gray-700">
      {source}
    </span>
  )
}

export default function MessageBubble({ role, content, sources, isStreaming }: Props) {
  const isUser = role === 'user'
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div className={`relative max-w-[80%] rounded-lg px-4 py-3 text-sm ${
        isUser ? 'bg-accent text-white' : 'bg-panel text-gray-200'
      }`}>
        {!isUser && sources && sources.length > 0 && (
          <div className="flex gap-1.5 flex-wrap mb-2">
            {sources.map((s, i) => <SourceTag key={i} source={s} />)}
          </div>
        )}
        {isUser ? (
          <p>{content}</p>
        ) : (
          <div className="prose prose-invert prose-sm max-w-none">
            <ReactMarkdown>{content}</ReactMarkdown>
            {isStreaming && (
              <span className="inline-block w-0.5 h-4 bg-gray-300 animate-pulse ml-0.5 align-middle" />
            )}
          </div>
        )}
      </div>
    </div>
  )
}

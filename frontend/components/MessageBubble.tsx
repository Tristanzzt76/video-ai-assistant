import ReactMarkdown from 'react-markdown'

interface Props {
  role: 'user' | 'assistant'
  content: string
  sources?: string[]
}

export default function MessageBubble({ role, content, sources }: Props) {
  const isUser = role === 'user'
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div className={`max-w-[80%] rounded-lg px-4 py-3 text-sm ${
        isUser ? 'bg-accent text-white' : 'bg-panel text-gray-200'
      }`}>
        {isUser ? (
          <p>{content}</p>
        ) : (
          <div className="prose prose-invert prose-sm max-w-none">
            <ReactMarkdown>{content}</ReactMarkdown>
          </div>
        )}
        {sources && sources.length > 0 && (
          <div className="mt-2 pt-2 border-t border-border text-xs text-gray-500">
            来源: {sources.join(', ')}
          </div>
        )}
      </div>
    </div>
  )
}

import Link from 'next/link'

export default function Navbar() {
  return (
    <nav className="border-b border-border bg-panel">
      <div className="container mx-auto px-4 max-w-5xl h-14 flex items-center justify-between">
        <span className="font-semibold text-sm">视频技术 AI 助手</span>
        <div className="flex gap-6 text-sm text-gray-400">
          <Link href="/" className="hover:text-white transition-colors">对话</Link>
          <Link href="/upload" className="hover:text-white transition-colors">上传文档</Link>
        </div>
      </div>
    </nav>
  )
}

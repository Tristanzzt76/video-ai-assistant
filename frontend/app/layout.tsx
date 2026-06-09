import type { Metadata } from 'next'
import './globals.css'
import Navbar from '@/components/Navbar'

export const metadata: Metadata = {
  title: '视频技术 AI 助手',
  description: 'RAG + LangGraph Agent 视频技术问答系统',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh">
      <body className="min-h-screen bg-surface">
        <Navbar />
        <main className="container mx-auto px-4 py-6 max-w-5xl">{children}</main>
      </body>
    </html>
  )
}

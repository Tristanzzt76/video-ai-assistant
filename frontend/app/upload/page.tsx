'use client'
import UploadZone from '@/components/UploadZone'

export default function UploadPage() {
  return (
    <div className="max-w-2xl mx-auto">
      <h1 className="text-xl font-semibold mb-6">上传文档</h1>
      <UploadZone />
    </div>
  )
}

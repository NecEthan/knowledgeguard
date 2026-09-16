import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'KnowledgeGuard',
  description: 'Enterprise knowledge platform — ask questions, get cited answers from your documents.',
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}

import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'

function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-background text-foreground flex flex-col">
        {/* Basic Header Placeholder */}
        <header className="border-b p-4 flex items-center justify-between">
          <h1 className="text-xl font-bold tracking-tight">RecruiteAI</h1>
          <Button variant="outline">Sign In</Button>
        </header>

        {/* Main Content Placeholder */}
        <main className="flex-1 p-8">
          <Routes>
            <Route path="/" element={
              <div className="max-w-2xl mx-auto text-center space-y-6 mt-20">
                <h2 className="text-4xl font-extrabold tracking-tight">AI-Powered Telephonic Interviews</h2>
                <p className="text-muted-foreground text-lg">Automate your screening process with our intelligent voice agent.</p>
                <Button size="lg" className="mt-4">Get Started</Button>
              </div>
            } />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}

export default App

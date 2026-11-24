import { Compass } from 'lucide-react'
import { Link } from 'react-router-dom'
import { EmptyState } from '../components/EmptyState'
import { Navbar } from '../components/Navbar'

export default function NotFound() {
  return (
    <>
      <Navbar variant="marketing" />
      <main className="mx-auto max-w-2xl px-4 py-16">
        <EmptyState icon={Compass} title="Page not found" description="That address doesn't exist in ContribMatch."
          action={<Link to="/" className="btn-primary">Back to home</Link>} />
      </main>
    </>
  )
}

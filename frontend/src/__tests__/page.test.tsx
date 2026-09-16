import { render, screen } from '@testing-library/react'
import Page from '../app/page'

describe('Home page', () => {
  it('renders the application heading', () => {
    render(<Page />)
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(
      'KnowledgeGuard',
    )
  })

  it('renders page content', () => {
    render(<Page />)
    expect(screen.getByText('Enterprise knowledge platform.')).toBeInTheDocument()
  })
})

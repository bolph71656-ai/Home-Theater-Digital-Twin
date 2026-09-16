import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import { ComparisonReportPanel } from './ComparisonReports'
import { PlacementOverviewPanel } from './PlacementOverview'
import './styles.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
    <ComparisonReportPanel />
    <PlacementOverviewPanel />
  </StrictMode>,
)

import { Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import { ScenarioProvider } from './context/ScenarioContext'
import Dashboard from './pages/Dashboard'
import FarmDetail from './pages/FarmDetail'
import PartnerApi from './pages/PartnerApi'
import RegisterFarm from './pages/RegisterFarm'

export default function App() {
  return (
    <ScenarioProvider>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="farms/:id" element={<FarmDetail />} />
          <Route path="register" element={<RegisterFarm />} />
          <Route path="partners" element={<PartnerApi />} />
          <Route path="*" element={<p className="text-stone-500">Page not found.</p>} />
        </Route>
      </Routes>
    </ScenarioProvider>
  )
}

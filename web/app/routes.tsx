import { Navigate, Route, Routes } from 'react-router-dom'
import type { ComponentType } from 'react'
import LeitorPage from '../features/leitura/LeitorPage'

type RouteComponents = {
  LoginPage: ComponentType
  ProfilePage: ComponentType<{ onSignOut: () => void }>
  ConsultPage: ComponentType
}

export function AppRoutes({ hasSession, onSignOut, LoginPage, ProfilePage, ConsultPage }: RouteComponents & {
  hasSession: boolean
  onSignOut: () => void
}) {
  return (
    <Routes>
      <Route path="/entrar" element={hasSession ? <Navigate to="/perfil" replace /> : <LoginPage />} />
      <Route path="/perfil" element={hasSession ? <ProfilePage onSignOut={onSignOut} /> : <Navigate to="/entrar" replace />} />
      <Route path="/consultar" element={hasSession ? <ConsultPage /> : <Navigate to="/entrar" replace />} />
      <Route path="/ler/:bookId" element={hasSession ? <LeitorPage /> : <Navigate to="/entrar" replace />} />
      <Route path="*" element={<Navigate to={hasSession ? '/perfil' : '/entrar'} replace />} />
    </Routes>
  )
}

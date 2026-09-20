import { AppRoutes } from './app/routes'
import { ProfileProvider } from './app/profile'
import { SessionProvider, useSession } from './app/session'
import EntrarPage from './features/entrar/EntrarPage'
import PerfilPage from './features/perfil/PerfilPage'
import ConsultaPage from './features/consulta/ConsultaPage'

function Application() {
  const { hasSession, signOut } = useSession()

  return (
    <div className="workspace-page">
      <div className="workspace-shell">
        <AppRoutes
          hasSession={hasSession}
          onSignOut={signOut}
          LoginPage={EntrarPage}
          ProfilePage={PerfilPage}
          ConsultPage={ConsultaPage}
        />
      </div>
    </div>
  )
}

export default function App() {
  return (
    <SessionProvider>
      <ProfileProvider>
        <Application />
      </ProfileProvider>
    </SessionProvider>
  )
}

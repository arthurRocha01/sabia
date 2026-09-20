import { AppRoutes } from './routes'
import { PrecisionProvider } from './precision'
import { ProfileProvider } from './profile'
import { SessionProvider, useSession } from './session'
import LoginPage from '../features/entrar/LoginPage'
import ProfilePage from '../features/perfil/ProfilePage'
import ConsultPage from '../features/consulta/ConsultPage'

function Application() {
  const { hasSession, signOut } = useSession()

  return (
    <div className="workspace-page">
      <div className="workspace-shell">
        <AppRoutes
          hasSession={hasSession}
          onSignOut={signOut}
          LoginPage={LoginPage}
          ProfilePage={ProfilePage}
          ConsultPage={ConsultPage}
        />
      </div>
    </div>
  )
}

export default function App() {
  return (
    <SessionProvider>
      <ProfileProvider>
        <PrecisionProvider>
          <Application />
        </PrecisionProvider>
      </ProfileProvider>
    </SessionProvider>
  )
}

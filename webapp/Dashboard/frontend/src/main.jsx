import { flushSync } from 'react-dom';
import { createRoot } from 'react-dom/client';
import { startWorkspace } from 'virtual:flowwatch-features';
import { Workspace } from './components/Workspace.jsx';
import './themes/dashboard.css';

const root = createRoot(document.getElementById('root'));
startWorkspace(snapshot => {
  flushSync(() => root.render(<Workspace {...snapshot} />));
});

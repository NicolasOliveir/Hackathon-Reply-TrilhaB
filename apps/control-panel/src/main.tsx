import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './app/App';
import './styles.css';
import './briefing.css';
import './stories.css';
createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>);

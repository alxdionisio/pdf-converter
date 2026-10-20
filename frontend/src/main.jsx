import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
// Self-hosted fonts: no request leaves the origin
import '@fontsource/dm-sans/300.css'
import '@fontsource/dm-sans/400.css'
import '@fontsource/dm-sans/500.css'
import '@fontsource/dm-mono/400.css'
import '@fontsource/dm-mono/500.css'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)

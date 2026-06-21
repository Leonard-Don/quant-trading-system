import React from 'react';
import ReactDOM from 'react-dom/client';
import { App as AntdApp } from 'antd';
import './index.css';
import './design/tailwind.css';
import App from './App';
import { ThemeProvider } from './contexts/ThemeContext';

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <React.StrictMode>
    <ThemeProvider>
      {/* Drop toasts below the ~64px fixed header so they stop covering the page
          title, and cap stacking so repeated failures don't pile up. */}
      <AntdApp message={{ top: 72, maxCount: 3 }}>
        <App />
      </AntdApp>
    </ThemeProvider>
  </React.StrictMode>
);

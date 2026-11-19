import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import "./styles.css";
import Booking from "./routes/Booking.jsx";
import Panel from "./routes/Panel.jsx";

const DEFAULT_SLUG = import.meta.env.VITE_DEFAULT_SLUG || "barbearia-mf";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to={`/${DEFAULT_SLUG}`} replace />} />
        <Route path="/:slug/painel" element={<Panel />} />
        <Route path="/:slug" element={<Booking />} />
      </Routes>
    </BrowserRouter>
  </React.StrictMode>
);

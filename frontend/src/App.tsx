import { useState } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import Sidebar from "./components/Sidebar";
import ChatTab from "./components/ChatTab";
import HistoryList from "./components/HistoryList";
import HistoryDetail from "./components/HistoryDetail";
import DatasetTab from "./components/DatasetTab";
import DetailPanel from "./components/DetailPanel";
import type { QueryResult, EntityDetail } from "./types";
import "./App.css";

export interface SelectedEntity {
  result?: QueryResult;
  detail?: EntityDetail;
}

function App() {
  const [selectedEntity, setSelectedEntity] = useState<SelectedEntity | null>(null);

  return (
    <>
      <div className="app">
        <Sidebar />
        <main className="main">
          <Routes>
            <Route path="/" element={<Navigate to="/chat" replace />} />
            <Route
              path="/chat"
              element={<ChatTab onEntitySelect={(r) => setSelectedEntity({ result: r })} />}
            />
            <Route
              path="/history"
              element={<HistoryList />}
            />
            <Route
              path="/history/:id"
              element={<HistoryDetail onEntitySelect={(r) => setSelectedEntity({ result: r })} />}
            />
            <Route
              path="/dataset"
              element={<DatasetTab onEntitySelect={(d) => setSelectedEntity({ detail: d })} />}
            />
          </Routes>
        </main>
      </div>
      <DetailPanel entity={selectedEntity} onClose={() => setSelectedEntity(null)} />
    </>
  );
}

export default App;

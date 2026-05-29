import { NavLink } from "react-router-dom";
import { FiZap, FiChevronsLeft, FiChevronsRight } from "react-icons/fi";
import { useState } from "react";
import "./Sidebar.css";

const tabs = [
  { to: "/chat", label: "Chat" },
  { to: "/history", label: "History" },
  { to: "/dataset", label: "Dataset" },
];

export default function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <aside className={`sidebar ${collapsed ? "collapsed" : ""}`}>
      <div className="sidebar-top">
        <div className="sidebar-logo">
          <span className="logo-icon"><FiZap size={16} /></span>
          {!collapsed && (
            <div className="logo-text-group">
              <span className="logo-text">Feeds.ai</span>
              <span className="logo-sub">Discovery</span>
            </div>
          )}
        </div>
        <button className="collapse-btn" onClick={() => setCollapsed(!collapsed)} title={collapsed ? "Expand" : "Collapse"}>
          {collapsed ? <FiChevronsRight size={16} /> : <FiChevronsLeft size={16} />}
        </button>
      </div>
      <div className="sidebar-divider" />
      <nav className="sidebar-nav">
        {tabs.map((tab) => (
          <NavLink
            key={tab.to}
            to={tab.to}
            className={({ isActive }) => `sidebar-tab ${isActive ? "active" : ""}`}
            title={collapsed ? tab.label : undefined}
          >
            <span className="tab-letter">{tab.label[0]}</span>
            {!collapsed && <span className="tab-label">{tab.label}</span>}
          </NavLink>
        ))}
      </nav>
      <div className="sidebar-footer">
        {!collapsed && <span className="sidebar-version">Pipeline v2.0</span>}
      </div>
    </aside>
  );
}

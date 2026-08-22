import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, type GmailStatus, type SystemStatus } from "../api";
import { useToast } from "../hooks/useToast";
import AISettings from "../components/settings/AISettings";
import CategorySettings from "../components/settings/CategorySettings";
import DataStorageSettings from "../components/settings/DataStorageSettings";
import GeneralSettings from "../components/settings/GeneralSettings";
import GmailSettings from "../components/settings/GmailSettings";
import SettingsNav, { SETTINGS_TAB_IDS, type SettingsTabId } from "../components/settings/SettingsNav";
import SystemSettings from "../components/settings/SystemSettings";

export default function SettingsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [gmail, setGmail] = useState<GmailStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { showToast } = useToast();

  const tabParam = searchParams.get("tab");
  const activeTab: SettingsTabId = tabParam && SETTINGS_TAB_IDS.has(tabParam) ? (tabParam as SettingsTabId) : "general";

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [system, gmailStatus] = await Promise.all([
        api.system(),
        api.gmailStatus(),
      ]);
      setStatus(system);
      setGmail(gmailStatus);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load system settings");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  function handleTabChange(tab: SettingsTabId) {
    setSearchParams({ tab });
  }

  if (error && !status) {
    return (
      <div className="settings-page-wrapper">
        <header className="settings-intro">
          <h1 className="settings-title">Settings</h1>
          <p className="error">Could not load settings: {error}</p>
        </header>
      </div>
    );
  }

  if (!status || !gmail) {
    return (
      <div className="settings-page-wrapper">
        <header className="settings-intro">
          <h1 className="settings-title">Settings</h1>
          <p className="empty">Loading settings…</p>
        </header>
      </div>
    );
  }

  return (
    <div className="settings-page-wrapper" style={{ animation: "rise 0.3s ease both" }}>
      {/* Page Header */}
      <header className="settings-intro">
        <h1 className="settings-title">Settings</h1>
        <p className="lead">
          Manage local ledger storage, Gmail integration, category taxonomy, and AI configuration.
        </p>
      </header>

      {/* Settings Tabbed Navigation */}
      <SettingsNav activeTab={activeTab} onTabChange={handleTabChange} />

      {/* Tab Content Panels */}
      <div className="settings-content-area" role="tabpanel" id={`settings-tabpanel-${activeTab}`}>
        {activeTab === "general" && <GeneralSettings status={status} />}
        {activeTab === "gmail" && (
          <GmailSettings
            status={status}
            gmail={gmail}
            loading={loading}
            onRefresh={refresh}
            onShowToast={showToast}
          />
        )}
        {activeTab === "categories" && <CategorySettings />}
        {activeTab === "ai" && <AISettings status={status} />}
        {activeTab === "data" && <DataStorageSettings status={status} onShowToast={showToast} />}
        {activeTab === "system" && <SystemSettings status={status} />}
      </div>
    </div>
  );
}
